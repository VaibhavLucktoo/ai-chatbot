"""Async Llama generation through an OpenAI-compatible chat endpoint.

Environment variables override values in the project's .env file:
    LLM_BASE_URL: API prefix, including /v1 (default: local Ollama).
    LLM_MODEL: The exact model name served by the provider.
    LLM_API_KEY: Optional bearer token; local Ollama needs no key.
    LLM_TIMEOUT_SECONDS: Total generation deadline (default: 30 seconds).
"""

import asyncio
from pathlib import Path

import httpx
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError


CONNECT_TIMEOUT_SECONDS = 5.0
EXECUTION_TIMEOUT_SECONDS = 30.0
MAX_OUTPUT_TOKENS = 300


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


def _request_settings() -> tuple[str, str, dict[str, str], float]:
    """Validate configuration without exposing URLs or credentials in errors."""
    try:
        settings = _LLMSettings()
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
    """Generate one text answer using the configured Llama provider.

    The connection timeout is 5 seconds. The entire HTTP operation, including
    connection setup and response reading, is bounded by LLM_TIMEOUT_SECONDS
    (30 seconds by default). Requests do not stream or retry automatically.
    Caller cancellation propagates. Trusted instructions can be supplied in a
    separate system message. Output is capped at 1,024 tokens; truncated output
    is rejected by the completion parser.

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
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    endpoint, model, headers, timeout_seconds = _request_settings()
    if trace is not None:
        trace.update(
            llm_model=model,
            generation={
                "temperature": 0, "max_tokens": MAX_OUTPUT_TOKENS,
                "timeout_seconds": timeout_seconds,
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
            async with httpx.AsyncClient(
                timeout=timeout,
                headers=headers,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    endpoint,
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0,
                        "max_tokens": MAX_OUTPUT_TOKENS,
                        "stream": False,
                    },
                )
    except (httpx.TimeoutException, TimeoutError):
        raise LLMTimeoutError("LLM request timed out.") from None
    except httpx.DecodingError:
        raise LLMResponseError("LLM response could not be decoded.") from None
    except (httpx.RequestError, httpx.InvalidURL):
        raise LLMConnectionError("Could not communicate with the LLM provider.") from None

    if trace is not None:
        trace["llm_http_status"] = response.status_code
        try:
            trace["llm_response"] = response.json()
        except (ValueError, UnicodeError):
            trace["llm_response_text"] = response.text
    return _extract_answer(response)
