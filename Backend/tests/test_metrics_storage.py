"""Real SQL aggregation, filtering, pagination and durable metric history."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
import httpx
from fastapi import FastAPI
from sqlalchemy.schema import CreateSchema, DropSchema
from app.api.v1.metrics import router
from app.core.config import get_settings
from app.services.metrics import RequestMeasurement, CallMeasurement
from app.storage.db import Database
from app.storage.metrics import read_metrics, write_metrics
from app.storage.models import ChatMetric, ModelCallMetric
from tests.helpers import AsyncTestCase, async_test


@unittest.skipUnless(os.environ.get("RUN_DB_TESTS") == "1", "Set RUN_DB_TESTS=1 for metric database checks")
class MetricsStorageTests(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.database = Database(get_settings())
        self.schema = "metrics_test_" + uuid4().hex
        self.created = False
        self.addCleanup(lambda: self.runner.run(self.cleanup_database()))
        self.runner.run(self.prepare_database())

    async def prepare_database(self):
        async with self.database.transaction() as connection:
            await connection.execute(CreateSchema(self.schema))
        self.created = True
        self.database._engine = self.database._engine.execution_options(schema_translate_map={None: self.schema})
        async with self.database.transaction() as connection:
            await connection.run_sync(ChatMetric.__table__.create)
            await connection.run_sync(ModelCallMetric.__table__.create)

    async def cleanup_database(self):
        try:
            if self.created:
                assert self.schema.startswith("metrics_test_")
                async with self.database.transaction() as connection:
                    await connection.execute(DropSchema(self.schema, cascade=True))
        finally:
            await self.database.close()

    def row(self, minutes=0, **kwargs):
        return RequestMeasurement(uuid4(), uuid4(), datetime.now(timezone.utc) - timedelta(minutes=minutes), "/v1/chat",
                                  **kwargs).rows()

    @async_test
    async def test_empty_is_unknown_not_perfect_accuracy_or_zero_tokens(self):
        data = await read_metrics(self.database)
        self.assertEqual(data["requests"]["total"], 0)
        self.assertIsNone(data["requests"]["success_rate"])
        self.assertIsNone(data["requests"]["p95_ms"])
        self.assertIsNone(data["calls"]["total_tokens"])

    @async_test
    async def test_aggregates_latency_partial_usage_cost_and_pagination(self):
        first = self.row(3, http_status=200, outcome="answered", intent="document_question", duration_ms=100,
                         retrieval_performed=True, result_count=5, source_count=2, stage_timings_ms={"retrieve": 10})
        second = self.row(2, http_status=429, outcome="provider_rate_limit", duration_ms=500)
        third = self.row(1, http_status=200, outcome="conversation", intent="conversation", duration_ms=200)
        first[1].append(dict(CallMeasurement(model="a", provider="provider.example", provider_requested=True,
                                            input_tokens=100, output_tokens=10, total_tokens=110, estimated_cost_usd=Decimal("0.001")).__dict__, request_id=first[0]["id"]))
        second[1].append(dict(CallMeasurement(model="a", status="error", http_status=429, provider_requested=True).__dict__, request_id=second[0]["id"]))
        second[1].append(dict(CallMeasurement(model="b", provider_requested=True, input_tokens=200, output_tokens=20, total_tokens=220).__dict__, request_id=second[0]["id"]))
        await write_metrics(self.database, [first, second, third])
        data = await read_metrics(self.database, limit=1, offset=1)
        self.assertEqual(data["requests"]["total"], 3)
        self.assertEqual(data["requests"]["success_rate"], 66.67)
        self.assertEqual(data["requests"]["median_ms"], 200)
        self.assertEqual(data["requests"]["p95_ms"], 470)
        self.assertEqual(data["calls"]["input_tokens"], 300)
        self.assertEqual(data["calls"]["rate_limited"], 1)
        self.assertEqual(data["calls"]["estimated_cost_usd"], 0.001)
        self.assertFalse(data["calls"]["usage_complete"])
        self.assertFalse(data["calls"]["cost_complete"])
        self.assertEqual(data["recent"]["items"][0]["id"], str(second[0]["id"]))
        self.assertEqual(len(data["recent"]["items"][0]["calls"]), 2)
        self.assertEqual(sum(bucket["requests"] for bucket in data["timeline"]), 3)
        self.assertEqual(data["workflow_stages_ms"]["retrieve"], 10)
        filtered = await read_metrics(self.database, model="a")
        self.assertEqual(filtered["requests"]["total"], 2)
        self.assertEqual(filtered["calls"]["provider_requests"], 2)
        self.assertEqual(filtered["available_models"], ["a", "b"])

    @async_test
    async def test_time_window_and_new_instance_restore_history(self):
        await write_metrics(self.database, [self.row(120, http_status=200, outcome="conversation")])
        self.assertEqual((await read_metrics(self.database, hours=1))["requests"]["total"], 0)
        other = Database(get_settings())
        other._engine = other._engine.execution_options(schema_translate_map={None: self.schema})
        try:
            self.assertEqual((await read_metrics(other, hours=24))["requests"]["total"], 1)
        finally:
            await other.close()

    @async_test
    async def test_assistant_revisions_filter_calls_without_multiplying_requests(self):
        identifier = uuid4()
        connection_id = uuid4()
        first = self.row(3, http_status=200, outcome="answered", duration_ms=100,
                         assistant_id=identifier, assistant_name="Historical assistant", assistant_revision=1,
                         connection_id=connection_id, connection_revision=1,
                         configured_provider="groq", configured_model="shared-model")
        for stage in ("answer", "review"):
            first[1].append(dict(CallMeasurement(stage=stage, model="shared-model", provider="api.groq.com",
                provider_requested=True, input_tokens=100, output_tokens=10, estimated_cost_usd=Decimal("0.001")).__dict__,
                request_id=first[0]["id"]))
        second = self.row(2, http_status=503, outcome="error", duration_ms=500,
                         assistant_id=identifier, assistant_name="Renamed assistant", assistant_revision=2,
                         connection_id=connection_id, connection_revision=2,
                         configured_provider="gemini", configured_model="shared-model")
        second[1].append(dict(CallMeasurement(model="shared-model", provider="generativelanguage.googleapis.com",
            provider_requested=True, status="error").__dict__, request_id=second[0]["id"]))
        third = self.row(1, http_status=200, outcome="conversation", duration_ms=50)
        await write_metrics(self.database, [first, second, third])
        data = await read_metrics(self.database, assistant_id=identifier)
        self.assertEqual(data["requests"]["total"], 2)
        by_revision = {item["assistant_revision"]: item for item in data["assistants"]}
        self.assertEqual(by_revision[1]["requests"], 1)
        self.assertEqual(by_revision[1]["provider_requests"], 2)
        self.assertEqual(by_revision[1]["p95_ms"], 100)
        self.assertEqual(by_revision[1]["estimated_cost_usd"], 0.002)
        self.assertTrue(by_revision[1]["cost_complete"])
        self.assertFalse(by_revision[2]["cost_complete"])
        self.assertEqual(data["available_assistants"], [{"id": str(identifier), "name": "Renamed assistant"}])
        self.assertEqual(data["recent"]["items"][0]["assistant_id"], str(identifier))
        filtered = await read_metrics(self.database, assistant_id=identifier, model="shared-model", provider="api.groq.com")
        self.assertEqual(filtered["requests"]["total"], 1)
        self.assertEqual(filtered["calls"]["provider_requests"], 2)
        self.assertEqual((await read_metrics(self.database, workspace_only=True))["requests"]["total"], 1)

    @async_test
    async def test_protected_api_returns_real_sql_data(self):
        await write_metrics(self.database, [self.row(http_status=200, outcome="conversation")])
        app = FastAPI()
        app.state.database = self.database
        app.state.admin_token = "token"
        app.include_router(router, prefix="/v1")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://127.0.0.1") as client:
            response = await client.get("/v1/admin/metrics", headers={"X-Admin-Token": "token"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["requests"]["total"], 1)
            self.assertEqual(response.json()["quality"]["status"], "not_evaluated")
            self.assertIsNone(response.json()["quality"]["accuracy"])
