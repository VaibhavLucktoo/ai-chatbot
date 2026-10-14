"""Request-scoped measurements and a bounded, best-effort persistence worker."""
import asyncio
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from time import perf_counter
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)
WORKFLOW_VERSION = "conversational-rag-v1"
_request = ContextVar("chat_measurement", default=None)
_call = ContextVar("model_call_measurement", default=None)
_stage = ContextVar("model_call_stage", default="answer")
NODES = {"route_intent", "resolve_follow_up", "retrieve", "select_context", "fallback", "prepare_prompt", "generate", "validate"}
INTENTS = {"conversation", "document_question", "follow_up", "unsupported"}
ERROR_TYPES = {"LLMTimeoutError", "LLMConnectionError", "LLMResponseError", "LLMRateLimitError", "RetrievalProviderError",
               "CancelledError", "NodeCancelledError", "TimeoutError", "SQLAlchemyError", "OperationalError", "IntegrityError",
               "ConversationBusyError", "ConversationAccessError", "ValidationError", "OSError"}


def safe_error(error):
    name = type(error).__name__ if isinstance(error, BaseException) else error
    return name if name in ERROR_TYPES else "InternalError"


def safe_usage(usage):
    usage = usage if isinstance(usage, dict) else {}
    # Ignore malformed, negative or absurd provider values, including booleans.
    return {target: value if type(value := usage.get(source)) is int and 0 <= value <= 2_000_000_000 else None
            for source, target in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens"), ("total_tokens", "total_tokens"))}


@dataclass
class CallMeasurement:
    id: UUID = field(default_factory=uuid4)
    stage: str = "answer"
    model: str | None = None
    provider: str | None = None
    status: str = "success"
    error_type: str | None = None
    provider_requested: bool = False
    http_status: int | None = None
    duration_ms: float = 0
    queue_ms: float | None = None
    provider_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None


@dataclass
class RequestMeasurement:
    id: UUID
    instance_id: UUID
    started_at: datetime
    endpoint: str
    workflow_version: str = WORKFLOW_VERSION
    prompt_version: str | None = None
    http_status: int | None = None
    outcome: str = "error"
    intent: str | None = None
    error_type: str | None = None
    duration_ms: float = 0
    graph_ms: float | None = None
    retrieval_performed: bool = False
    result_count: int = 0
    source_count: int = 0
    stage_timings_ms: dict = field(default_factory=dict)
    calls: list[CallMeasurement] = field(default_factory=list)
    collector: object = field(default=None, repr=False)
    assistant_id: UUID | None = None
    assistant_name: str | None = None
    assistant_revision: int | None = None
    connection_id: UUID | None = None
    connection_revision: int | None = None
    configured_provider: str | None = None
    configured_model: str | None = None

    def rows(self):
        # Explicit allowlists keep live resources, private traces and content out of SQL.
        request = {name: getattr(self, name) for name in (
            "id", "instance_id", "started_at", "endpoint", "workflow_version", "prompt_version", "http_status",
            "outcome", "intent", "error_type", "duration_ms", "graph_ms", "retrieval_performed", "result_count", "source_count", "stage_timings_ms",
            "assistant_id", "assistant_name", "assistant_revision", "connection_id", "connection_revision", "configured_provider", "configured_model")}
        calls = [dict(asdict(call), request_id=self.id) for call in self.calls]
        return request, calls


def current_request():
    return _request.get()


def current_call():
    return _call.get()


@contextmanager
def model_stage(stage):
    if stage not in {"answer", "review", "follow_up"}:
        raise ValueError("Unknown model-call stage")
    token = _stage.set(stage)
    try:
        yield
    finally:
        _stage.reset(token)


@contextmanager
def measure_call():
    request = current_request()
    if request is None:
        yield None
        return
    call = CallMeasurement(stage=_stage.get())
    token = _call.set(call)
    started = perf_counter()
    try:
        yield call
    except BaseException as error:
        call.status = "cancelled" if isinstance(error, asyncio.CancelledError) else "error"
        call.error_type = safe_error(error)
        raise
    finally:
        call.duration_ms = round((perf_counter() - started) * 1000, 2)
        price = request.collector.settings.metrics_model_prices.get(call.model)
        if price is not None and call.input_tokens is not None and call.output_tokens is not None:
            call.estimated_cost_usd = ((Decimal(call.input_tokens) * Decimal(str(price.input_usd_per_million))
                                       + Decimal(call.output_tokens) * Decimal(str(price.output_usd_per_million))) / Decimal(1_000_000))
        request.calls.append(call)
        _call.reset(token)


def record_graph(trace, *, prompt_version, error=None):
    request = current_request()
    if request is None:
        return
    request.prompt_version = prompt_version
    request.intent = trace.get("intent") if trace.get("intent") in INTENTS else None
    request.graph_ms = trace.get("total_ms")
    request.retrieval_performed = trace.get("retrieval_performed") is True
    request.result_count = trace.get("result_count", 0)
    request.source_count = len((trace.get("response") or {}).get("sources", []))
    request.stage_timings_ms = {name: value for name, value in trace.get("timings_ms", {}).items() if name in NODES}
    if error is not None:
        request.error_type = safe_error(error)
    fallback = trace.get("fallback_category")
    if fallback == "insufficient_evidence":
        request.outcome = "insufficient_context"
    elif fallback in {"document_selection", "unresolved_reference"}:
        request.outcome = "clarification_required"
    else:
        request.outcome = request.intent if request.intent in {"conversation", "unsupported"} else "answered"


def classify_request(request, error):
    if isinstance(error, asyncio.CancelledError):
        return "cancelled"
    code = request.http_status
    if code is not None and 200 <= code < 300:
        return request.outcome
    if code == 429:
        return "provider_rate_limit" if any(call.http_status == 429 for call in request.calls) else "capacity_rejected"
    return {400: "invalid_request", 403: "access_denied", 408: "timeout", 409: "conversation_busy", 422: "invalid_request", 413: "invalid_request",
            504: "timeout", 503: "dependency_unavailable", 502: "invalid_model_response"}.get(code, "error")


class MetricsCollector:
    def __init__(self, database):
        self.database, self.settings = database, database.settings
        self.instance_id = uuid4()
        self.started_at = datetime.now(timezone.utc)
        self.queue = asyncio.Queue(maxsize=self.settings.metrics_queue_capacity)
        self.active_chats = self.active_model_calls = self.waiting_model_calls = 0
        self.inflight_metric_writes = 0
        self.dropped_events = self.write_failures = self.persisted_events = 0
        self.last_write_at = self.last_error = None
        self.worker = None

    def start(self):
        self.worker = asyncio.create_task(self._write_loop(), name="model-metrics-writer")

    @contextmanager
    def request(self, endpoint):
        measurement = RequestMeasurement(uuid4(), self.instance_id, datetime.now(timezone.utc), endpoint, collector=self)
        token = _request.set(measurement)
        start, error = perf_counter(), None
        self.active_chats += 1
        try:
            yield measurement
        except BaseException as exc:
            error = exc
            measurement.error_type = safe_error(exc)
            raise
        finally:
            measurement.duration_ms = round((perf_counter() - start) * 1000, 2)
            measurement.outcome = classify_request(measurement, error)
            self.active_chats -= 1
            _request.reset(token)
            try:
                self.queue.put_nowait(measurement.rows())
            except asyncio.QueueFull:
                self.dropped_events += 1

    def snapshot(self):
        return {"scope": "this_process", "instance_id": str(self.instance_id), "started_at": self.started_at.isoformat(),
                "active_chats": self.active_chats, "active_model_calls": self.active_model_calls,
                "waiting_model_calls": self.waiting_model_calls,
                "pending_metric_writes": self.queue.qsize() + self.inflight_metric_writes,
                "dropped_events": self.dropped_events, "write_failures": self.write_failures,
                "persisted_events": self.persisted_events,
                "last_write_at": self.last_write_at.isoformat() if self.last_write_at else None,
                "last_error": self.last_error,
                "writer_running": self.worker is not None and not self.worker.done()}

    async def _write_loop(self):
        from app.storage.metrics import write_metrics
        while True:
            batch = [await self.queue.get()]
            while len(batch) < 100 and not self.queue.empty():
                batch.append(self.queue.get_nowait())
            self.inflight_metric_writes = len(batch)
            try:
                async with asyncio.timeout(self.settings.metrics_write_timeout_seconds):
                    await write_metrics(self.database, batch)
                self.persisted_events += len(batch)
                self.last_write_at, self.last_error = datetime.now(timezone.utc), None
            except asyncio.CancelledError:
                self.dropped_events += len(batch)
                raise
            except Exception as error:
                self.write_failures += 1
                self.dropped_events += len(batch)
                self.last_error = safe_error(error)
                logger.warning("Metrics write failed (%s); dropped_events=%d", self.last_error, self.dropped_events)
            finally:
                self.inflight_metric_writes = 0
                for _ in batch:
                    self.queue.task_done()

    async def close(self):
        if self.worker is None:
            return
        try:
            async with asyncio.timeout(5):
                await self.queue.join()
        except TimeoutError:
            pass
        self.worker.cancel()
        try:
            await self.worker
        except asyncio.CancelledError:
            pass
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
            self.dropped_events += 1
