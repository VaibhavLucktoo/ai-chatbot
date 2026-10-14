"""Async LangChain generation through a validated OpenAI-compatible endpoint.

Environment variables override values in the project's .env file:
    LLM_BASE_URL: API prefix, including /v1 (default: local Ollama).
    LLM_MODEL: The exact model name served by the provider.
    LLM_API_KEY: Optional bearer token; local Ollama needs no key.
    LLM_TIMEOUT_SECONDS: Total generation deadline (default: 30 seconds).
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from time import perf_counter

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError

from app.providers.chat_model import CompatibleChatModel
from app.providers.registry import ProviderModelSettings
from app.services.metrics import current_call, current_request, measure_call, safe_usage


CONNECT_TIMEOUT_SECONDS = 5.0
EXECUTION_TIMEOUT_SECONDS = 30.0
MAX_OUTPUT_TOKENS = 300
_shared_client: ContextVar[httpx.AsyncClient | None] = ContextVar("llm_client", default=None)
_shared_slots: ContextVar[asyncio.Semaphore | None] = ContextVar("llm_slots", default=None)
_model_override: ContextVar[ProviderModelSettings | None] = ContextVar("assistant_model", default=None)


@contextmanager
def assistant_model_resources(settings: ProviderModelSettings | None):
    """One immutable configuration for every model stage in this request."""
    token = _model_override.set(settings)
    try:
        yield
    finally:
        _model_override.reset(token)


def effective_model_settings() -> ProviderModelSettings | _LLMSettings:
    return _model_override.get() or _LLMSettings()


@contextmanager
def llm_request_resources(client, slots):
    """Bind application-owned resources without sharing request traces."""
    client_token, slots_token = _shared_client.set(client), _shared_slots.set(slots)
    try:
        yield
    finally:
        _shared_client.reset(client_token)
        _shared_slots.reset(slots_token)


class LLMError(RuntimeError):
    """Base exception for LLM provider failures."""


class LLMConnectionError(LLMError):
    """The provider configuration is invalid or communication failed."""


class LLMTimeoutError(LLMError):
    """A network timeout or the total execution deadline was reached."""


class LLMResponseError(LLMError):
    """The provider returned an HTTP error or an unusable completion."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMRateLimitError(LLMResponseError):
    """The LLM provider rejected the request because of a rate limit."""

    def __init__(self, message: str = "LLM provider rate limit exceeded.") -> None:
        super().__init__(message, status_code=429)


class _LLMSettings(BaseSettings):
    """Load LLM settings independently of database configuration."""

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        str_strip_whitespace=True,
        hide_input_in_errors=True,
    )

    base_url: str = Field(default="http://127.0.0.1:11434/v1", min_length=1)
    model: str = Field(default="llama3.2:1b-instruct-q4_K_M", min_length=1)
    api_key: SecretStr = SecretStr("")
    timeout_seconds: float = Field(
        default=EXECUTION_TIMEOUT_SECONDS, gt=0, le=600, allow_inf_nan=False,
    )
    max_output_tokens: int | None = Field(default=None, ge=64, le=8192)
    temperature: float = Field(default=0, ge=0, le=2, allow_inf_nan=False)
    max_input_bytes: int = Field(default=64000, ge=2000, le=256000)
    context_window_tokens: int = Field(default=32768, ge=4096, le=1048576,
                                       validation_alias="RAG_CONTEXT_WINDOW_TOKENS")


def _request_settings() -> tuple[str, str, dict[str, str], float]:
    """Validate configuration without exposing URLs or credentials in errors."""
    try:
        settings = effective_model_settings()
        base_url = httpx.URL(settings.base_url)
    except (ValidationError, SettingsError, httpx.InvalidURL, OSError, UnicodeError):
        raise LLMConnectionError(
            "Invalid LLM configuration. Check LLM_BASE_URL, LLM_MODEL, "
            "LLM_API_KEY, and LLM_TIMEOUT_SECONDS."
        ) from None

    if (
        base_url.scheme not in {"http", "https"}
        or not base_url.host
        or base_url.username
        or base_url.password
        or base_url.query
        or base_url.fragment
    ):
        raise LLMConnectionError(
            "LLM_BASE_URL must be an absolute HTTP(S) API base URL "
            "without credentials, a query string, or a fragment."
        )

    api_key = settings.api_key.get_secret_value().strip()
    if any(ord(character) < 33 or ord(character) > 126 for character in api_key):
        raise LLMConnectionError(
            "LLM_API_KEY must contain only printable ASCII characters "
            "without whitespace."
        )

    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    endpoint = str(base_url).rstrip("/") + "/chat/completions"
    return endpoint, settings.model, headers, settings.timeout_seconds


def _extract_answer(response: httpx.Response) -> str:
    """Require a nonempty text completion and reject explicit partial output."""
    if response.status_code == 429:
        raise LLMRateLimitError()

    if not response.is_success:
        raise LLMResponseError(
            f"LLM provider returned HTTP {response.status_code}.",
            status_code=response.status_code,
        )

    try:
        payload = response.json()
    except (ValueError, UnicodeError):
        raise LLMResponseError("LLM provider returned invalid JSON.") from None

    if not isinstance(payload, dict) or payload.get("error") is not None:
        raise LLMResponseError("LLM provider returned an invalid completion.")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMResponseError("LLM provider returned no completion choices.")

    choice = choices[0]
    if not isinstance(choice, dict):
        raise LLMResponseError("LLM provider returned an invalid choice.")

    if choice.get("finish_reason") not in (None, "stop"):
        raise LLMResponseError(
            "LLM generation ended without a complete text answer."
        )

    message = choice.get("message")
    if not isinstance(message, dict):
        raise LLMResponseError("LLM provider returned an invalid message.")

    if message.get("role") not in (None, "assistant"):
        raise LLMResponseError("LLM provider returned an invalid message role.")

    # Some compatible providers omit finish_reason. Do not mistake a refusal
    # or a message that requests tool execution for a completed answer.
    if message.get("refusal"):
        raise LLMResponseError("LLM provider refused to answer the request.")
    if message.get("tool_calls") or message.get("function_call"):
        raise LLMResponseError("LLM provider returned an unsupported tool request.")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise LLMResponseError("LLM provider returned an empty or non-text answer.")

    return content.strip()


async def generate_llm_response(
    prompt: str, *, system_prompt: str | None = None, trace: dict | None = None,
) -> str:
    """Generate one text answer through the LangChain chat-model interface.

    The connection timeout is 5 seconds. The entire HTTP operation, including
    connection setup and response reading, is bounded by LLM_TIMEOUT_SECONDS
    (30 seconds by default). Requests do not stream or retry automatically.
    Caller cancellation propagates. Trusted instructions can be supplied in a
    separate system message. GPT-OSS receives a 2,048-token budget including
    reasoning; other models use MAX_OUTPUT_TOKENS. Truncated output is rejected.

    Raises:
        ValueError: A supplied prompt is not a nonempty string.
        LLMConnectionError: Invalid configuration or a transport failure.
        LLMTimeoutError: A network timeout or execution deadline was reached.
        LLMResponseError: HTTP failure, malformed response, or incomplete answer.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a nonempty string.")
    if system_prompt is not None and (
        not isinstance(system_prompt, str) or not system_prompt.strip()
    ):
        raise ValueError("system_prompt must be a nonempty string when supplied.")

    messages = []
    if system_prompt is not None:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=prompt))

    async def transport(payload, **_options):
        # Keep the private diagnostic dictionary out of callback invocation kwargs.
        diagnostic = trace if trace is not None else {}
        answer = await _generate_completion(payload, trace=diagnostic)
        return answer, {
            key: diagnostic[key] for key in ("llm_model", "token_usage", "finish_reason") if key in diagnostic
        }

    response = await CompatibleChatModel(transport=transport, model_name=_request_settings()[1], cache=False).ainvoke(messages)
    return response.content


async def _generate_completion(messages: list[dict], *, trace: dict | None = None) -> str:
    with measure_call():
        return await _perform_completion(messages, trace=trace)


async def _perform_completion(messages: list[dict], *, trace: dict | None = None) -> str:
    """Validated transport used by the LangChain chat-model adapter."""

    endpoint, model, headers, timeout_seconds = _request_settings()
    settings = effective_model_settings()
    measurement = current_call()
    request_metric = current_request()
    collector = request_metric.collector if request_metric else None
    if measurement is not None:
        measurement.model, measurement.provider = model[:200], httpx.URL(endpoint).host[:255]
    input_bytes = sum(len(item["content"].encode("utf-8")) for item in messages)
    if input_bytes > settings.max_input_bytes:
        raise LLMResponseError("The model input exceeds the configured size budget.")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": settings.temperature,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "stream": False,
    }
    if model in {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}:
        payload.update(max_tokens=2048, reasoning_effort="low")
    if settings.max_output_tokens is not None:
        payload["max_tokens"] = settings.max_output_tokens
    if input_bytes + payload["max_tokens"] + 512 > settings.context_window_tokens:
        raise LLMResponseError("The input and output budget exceed the configured model context window.")
    if trace is not None:
        trace.update(
            llm_model=model,
            generation={
                "temperature": payload["temperature"], "max_tokens": payload["max_tokens"],
                "timeout_seconds": timeout_seconds,
                "input_bytes": input_bytes,
                **({"reasoning_effort": payload["reasoning_effort"]}
                   if "reasoning_effort" in payload else {}),
            },
        )
    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT_SECONDS,
        read=timeout_seconds,
        write=timeout_seconds,
        pool=CONNECT_TIMEOUT_SECONDS,
    )

    try:
        async with asyncio.timeout(timeout_seconds):
            slots = _shared_slots.get()
            queued = perf_counter()
            if collector is not None and slots is not None:
                collector.waiting_model_calls += 1
            try:
                if slots is not None:
                    await slots.acquire()
            finally:
                if measurement is not None:
                    measurement.queue_ms = round((perf_counter() - queued) * 1000, 2)
                if collector is not None and slots is not None:
                    collector.waiting_model_calls -= 1
            try:
                queue_ms = round((perf_counter() - queued) * 1000, 2)
                if measurement is not None:
                    measurement.queue_ms = queue_ms
                if trace is not None:
                    trace["generation_queue_ms"] = queue_ms
                if measurement is not None:
                    measurement.provider_requested = True
                if collector is not None:
                    collector.active_model_calls += 1
                provider_started = perf_counter()
                try:
                    client = _shared_client.get()
                    if client is not None:
                        response = await client.post(endpoint, json=payload, headers=headers, timeout=timeout)
                    else:
                        # CLI and standalone callers retain a short, owned client.
                        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=False) as client:
                            response = await client.post(endpoint, json=payload)
                finally:
                    if measurement is not None:
                        measurement.provider_ms = round((perf_counter() - provider_started) * 1000, 2)
                    if collector is not None:
                        collector.active_model_calls -= 1
            finally:
                if slots is not None:
                    slots.release()
    except (httpx.TimeoutException, TimeoutError):
        raise LLMTimeoutError("LLM request timed out.") from None
    except httpx.DecodingError:
        raise LLMResponseError("LLM response could not be decoded.") from None
    except (httpx.RequestError, httpx.InvalidURL):
        raise LLMConnectionError("Could not communicate with the LLM provider.") from None

    if measurement is not None:
        measurement.http_status = response.status_code
        try:
            body = response.json()
            usage = safe_usage(body.get("usage") if isinstance(body, dict) else None)
            for name, value in usage.items():
                setattr(measurement, name, value)
        except (ValueError, UnicodeError):
            pass
    if trace is not None:
        trace["llm_http_status"] = response.status_code
        try:
            trace["llm_response"] = response.json()
            choices = trace["llm_response"].get("choices", []) if isinstance(trace["llm_response"], dict) else []
            if choices and isinstance(choices[0], dict):
                trace["finish_reason"] = choices[0].get("finish_reason")
            usage = trace["llm_response"].get("usage") if isinstance(trace["llm_response"], dict) else None
            if isinstance(usage, dict):
                trace["token_usage"] = {
                    key: value for key, value in usage.items()
                    if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                    and type(value) is int and value >= 0
                }
        except (ValueError, UnicodeError):
            trace["llm_response_text"] = response.text
    return _extract_answer(response)
