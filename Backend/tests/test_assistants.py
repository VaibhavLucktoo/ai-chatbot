"""Credential protection, explicit provider errors and concurrent configuration isolation."""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from cryptography.fernet import Fernet
import httpx
from fastapi import FastAPI
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.chat import get_db_session
from app.api.v1.router import api_router
from app.core.config import Settings
from app.providers.registry import provider_settings
from app.schemas.assistants import AssistantWrite, ConnectionCreate
from app.services import llm, rag, conversation_intent
from app.services.assistants import AssistantRuntime
from app.services.assistants import AssistantNotFound, AssistantAccessError
from app.services.credential_vault import CredentialError, CredentialVault
from tests.test_rag_service import stored_chunk
from tests.test_conversation import previous_turn


def vault_settings(path: Path, key: str = "") -> Settings:
    return Settings(_env_file=None, postgres_db="test", postgres_user="test", postgres_password="test",
                    assistant_key_file=path, assistant_encryption_key=key)


class VaultTests(unittest.TestCase):
    def test_encrypted_keys_are_bound_to_connection_and_provider_and_survive_restart(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "private" / "master.key"
            settings = vault_settings(path)
            vault = CredentialVault(settings)
            identifier = str(uuid4())
            token = vault.encrypt(SecretStr("private-provider-key"), provider="groq", connection_id=identifier)
            self.assertNotIn("private-provider-key", token)
            self.assertTrue(path.exists())
            self.assertEqual(CredentialVault(settings).decrypt(token, provider="groq", connection_id=identifier).get_secret_value(),
                             "private-provider-key")
            for provider, other_id in (("gemini", identifier), ("groq", str(uuid4()))):
                with self.assertRaises(CredentialError):
                    vault.decrypt(token, provider=provider, connection_id=other_id)
            path.unlink()
            with self.assertRaises(CredentialError):
                vault.decrypt(token, provider="groq", connection_id=identifier)
            self.assertFalse(path.exists(), "A missing decryption key must not be silently replaced")

    def test_configured_master_key_and_tampering(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "unused.key"
            vault = CredentialVault(vault_settings(path, Fernet.generate_key().decode()))
            token = vault.encrypt(SecretStr("private-key"), provider="gemini", connection_id="connection")
            self.assertFalse(path.exists())
            with self.assertRaises(CredentialError):
                vault.decrypt(token[:-4] + "AAAA", provider="gemini", connection_id="connection")

    def test_configuration_rejects_unsafe_keys_and_impossible_context(self):
        for key in ("", "key with spaces", "key\n", "non-ascii-ÿ"):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                ConnectionCreate(name="test", provider="groq", api_key=key)
        with self.assertRaises(ValidationError):
            AssistantWrite(name="test", model="model", connection_id=uuid4(),
                           context_window_tokens=4096, max_output_tokens=4096)


class AssistantApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/v1")
        self.app.state.admin_token = "local-test-token"
        self.app.state.database = SimpleNamespace()
        self.app.state.llm_slots = asyncio.Semaphore(2)
        self.db = AsyncMock(spec=AsyncSession)

        async def session():
            yield self.db
        self.app.dependency_overrides[get_db_session] = session
        @asynccontextmanager
        async def no_lease(database, identifier):
            yield
        guard = patch("app.api.v1.chat.stateless_assistant_turn", no_lease)
        guard.start()
        self.addCleanup(guard.stop)

    def client(self):
        return httpx.AsyncClient(transport=httpx.ASGITransport(self.app), base_url="http://127.0.0.1")

    async def test_configuration_requires_admin_and_validation_never_echoes_keys(self):
        async with self.client() as client:
            for method, path, payload in (
                ("GET", "/v1/admin/connections", None),
                ("GET", "/v1/admin/assistants", None),
                ("GET", "/v1/admin/providers", None),
                ("POST", "/v1/admin/connections", {"name": "test", "provider": "groq", "api_key": "secret"}),
                ("POST", "/v1/admin/assistants", {"name": "test", "model": "test", "connection_id": str(uuid4())}),
            ):
                response = await client.request(method, path, json=payload)
                self.assertEqual(response.status_code, 403)
            private = "secret invalid key"
            response = await client.post("/v1/admin/connections", headers={"X-Admin-Token": "local-test-token"},
                                         json={"name": "test", "provider": "groq", "api_key": private})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(private, response.text)
            self.assertNotIn('"input"', response.text)
            response = await client.post("/v1/admin/connections", headers={"X-Admin-Token": "local-test-token"},
                                         json={"name": "test", "provider": "groq", "api_key": "secret-key", "unknown": "private-extra"})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("private-extra", response.text)

    async def test_provider_test_maps_failures_without_exposing_provider_body(self):
        for status, expected in ((401, 422), (404, 422), (429, 429), (500, 502)):
            with self.subTest(status=status):
                self.app.state.llm_client = httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(status, json={"error": "private-provider-body"})))
                try:
                    async with self.client() as client:
                        response = await client.post("/v1/admin/connections/test", headers={"X-Admin-Token": "local-test-token"},
                            json={"provider": "groq", "api_key": "private-key", "model": "openai/gpt-oss-120b"})
                    self.assertEqual(response.status_code, expected, response.text)
                    self.assertNotIn("private-key", response.text)
                    self.assertNotIn("private-provider-body", response.text)
                finally:
                    await self.app.state.llm_client.aclose()

    async def test_assistant_configuration_isolated_through_resolution_answer_and_review(self):
        assistants = {}
        for provider, model in (("groq", "openai/gpt-oss-120b"), ("gemini", "gemini-test")):
            identifier, connection, document = uuid4(), uuid4(), uuid4()
            assistants[identifier] = AssistantRuntime(identifier, 1, connection, 1, (document,),
                provider_settings(provider, model, SecretStr(provider + "-private-key")))
        seen = []
        async def load(database, identifier, selected):
            return assistants[identifier]
        async def retrieve(**kwargs):
            document = kwargs["allowed_document_ids"][0]
            chunk = asdict(stored_chunk(content="First step: open Events. Second step: choose Create."))
            chunk["document_id"] = document
            return [chunk]
        async def generate(*args, **kwargs):
            config = llm.effective_model_settings()
            await asyncio.sleep(0)
            seen.append((config.model, config.api_key.get_secret_value()))
            return json.dumps({"answer": config.model, "source_numbers": [1]})
        with patch("app.api.v1.chat.load_assistant_runtime", side_effect=load), \
             patch.object(rag, "search_similar_chunks", side_effect=retrieve), \
             patch.object(rag, "generate_llm_response", side_effect=generate):
            async with self.client() as client:
                responses = await asyncio.gather(*[client.post("/v1/chat", json={
                    "question": "What steps are required and why?", "assistant_id": str(identifier)
                }) for identifier in assistants])
        for runtime, response in zip(assistants.values(), responses):
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["sources"][0]["document_id"], str(runtime.document_ids[0]))
            self.assertEqual(response.json()["answer"], runtime.model_settings.model + " [1]")
            self.assertEqual(seen.count((runtime.model_settings.model, runtime.model_settings.api_key.get_secret_value())), 2)
        self.assertIsNone(llm._model_override.get())

    async def test_provider_transport_uses_request_configuration_without_crossing_keys(self):
        recorded = []
        async def handler(request):
            await asyncio.sleep(0)
            recorded.append((request.url.host, request.headers["Authorization"], json.loads(request.content)["model"]))
            return httpx.Response(200, json={"choices": [{"message": {"content": "Ready"}, "finish_reason": "stop"}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as provider_client:
            async def call(provider, model):
                config = provider_settings(provider, model, SecretStr(provider + "-key"))
                with llm.assistant_model_resources(config), llm.llm_request_resources(provider_client, asyncio.Semaphore(2)):
                    return await llm.generate_llm_response("Test")
            self.assertEqual(await asyncio.gather(call("groq", "openai/gpt-oss-120b"), call("gemini", "gemini-test")), ["Ready", "Ready"])
        self.assertCountEqual(recorded, [("api.groq.com", "Bearer groq-key", "openai/gpt-oss-120b"),
                                         ("generativelanguage.googleapis.com", "Bearer gemini-key", "gemini-test")])

    async def test_chat_telemetry_snapshots_configuration_without_credentials_or_documents(self):
        from app.api.v1.chat import run_chat
        from app.schemas.chat import ChatRequest, ChatResponse
        from app.services.metrics import MetricsCollector
        identifier, document, connection = uuid4(), uuid4(), uuid4()
        runtime = AssistantRuntime(identifier, 4, connection, 3, (document,),
            provider_settings("groq", "test-model", SecretStr("PRIVATE_KEY")), "HR", "groq")
        metrics = MetricsCollector(SimpleNamespace(settings=SimpleNamespace(
            metrics_queue_capacity=10, metrics_write_timeout_seconds=1, metrics_model_prices={})))
        with metrics.request("/v1/chat") as measurement, \
             patch("app.api.v1.chat.load_assistant_runtime", return_value=runtime), \
             patch("app.api.v1.chat.answer_question", return_value=ChatResponse(answer="PRIVATE_ANSWER", sources=[])):
            await run_chat(self.db, ChatRequest(question="PRIVATE_QUESTION", assistant_id=identifier),
                           conversation_database=self.app.state.database)
            measurement.http_status = 200
        row, calls = metrics.queue.get_nowait()
        self.assertEqual(row["assistant_id"], identifier)
        self.assertEqual(row["assistant_name"], "HR")
        self.assertEqual(row["assistant_revision"], 4)
        self.assertEqual(row["connection_revision"], 3)
        self.assertEqual(row["configured_provider"], "groq")
        self.assertEqual(row["configured_model"], "test-model")
        self.assertNotIn("PRIVATE_", str((row, calls)))
        self.assertNotIn(str(document), str(row))

    async def test_unavailable_assistants_never_fall_back_to_workspace_model(self):
        for error, status in ((AssistantNotFound("Assistant is missing or disabled."), 404),
                              (AssistantAccessError("Documents are not assigned."), 403),
                              (CredentialError("Saved key is unavailable."), 503)):
            with self.subTest(status=status), patch("app.api.v1.chat.load_assistant_runtime", side_effect=error), \
                 patch("app.api.v1.chat.answer_question") as generate:
                async with self.client() as client:
                    response = await client.post("/v1/chat", json={"question": "Question", "assistant_id": str(uuid4())})
                self.assertEqual(response.status_code, status)
                generate.assert_not_awaited()

    async def test_delete_endpoints_require_admin_and_return_empty_success_or_conflict(self):
        from app.services.assistants import AssistantConflict
        for resource, operation in (("assistants", "delete_assistant"), ("connections", "delete_connection")):
            path = f"/v1/admin/{resource}/{uuid4()}"
            async with self.client() as client:
                with patch(f"app.api.v1.assistants.{operation}") as remove:
                    denied = await client.delete(path)
                    self.assertEqual(denied.status_code, 403)
                    remove.assert_not_awaited()
                    response = await client.delete(path, headers={"X-Admin-Token": "local-test-token"})
                    self.assertEqual(response.status_code, 204)
                    self.assertEqual(response.content, b"")
                with patch(f"app.api.v1.assistants.{operation}", side_effect=AssistantConflict("Configuration is in use.")):
                    response = await client.delete(path, headers={"X-Admin-Token": "local-test-token"})
                    self.assertEqual(response.status_code, 409)
                with patch(f"app.api.v1.assistants.{operation}", side_effect=AssistantNotFound("Configuration not found.")):
                    response = await client.delete(path, headers={"X-Admin-Token": "local-test-token"})
                    self.assertEqual(response.status_code, 404)

    async def test_follow_up_uses_assistant_model_and_current_document_scope(self):
        identifier, document = uuid4(), uuid4()
        runtime = AssistantRuntime(identifier, 1, uuid4(), 1, (document,),
            provider_settings("gemini", "gemini-test", SecretStr("gemini-private-key")))
        turn = previous_turn(document_ids=(str(document),))
        chunk = asdict(stored_chunk())
        chunk["document_id"] = document
        observed = []
        async def resolve(*args, **kwargs):
            observed.append(llm.effective_model_settings().model)
            return '{"question":"Where are vectors stored?","needs_clarification":false}'
        async def generate(*args, **kwargs):
            observed.append(llm.effective_model_settings().model)
            return '{"answer":"In PostgreSQL.","source_numbers":[1]}'
        with llm.assistant_model_resources(runtime.model_settings), \
             patch.object(conversation_intent, "generate_llm_response", side_effect=resolve), \
             patch.object(rag, "generate_llm_response", side_effect=generate), \
             patch.object(rag, "search_similar_chunks", return_value=[chunk]) as retrieve:
            await rag.answer_question(self.db, rag.ChatRequest(question="Explain that", assistant_id=identifier),
                                      history=(turn,), assistant=runtime)
        self.assertEqual(observed, ["gemini-test", "gemini-test"])
        self.assertEqual(retrieve.await_args.kwargs["allowed_document_ids"], (document,))
