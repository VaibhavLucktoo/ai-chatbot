"""Shared sanitized HTTP error mapping, independent of endpoint modules."""

from collections.abc import Callable

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.services.configuration_errors import (
    AssistantAccessError,
    AssistantConfigurationError,
    AssistantConflict,
    AssistantNotFound,
)
from app.services.credential_vault import CredentialError
from app.services.llm import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)


class ConfigurationRoute(APIRoute):
    """Sanitize configuration failures; subclasses select legacy wire messages."""

    storage_error_detail = "Configuration storage is temporarily unavailable."

    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # FastAPI's default includes raw input, which may contain API keys.
                return JSONResponse(
                    {
                        "detail": [
                            {
                                "loc": error["loc"],
                                "msg": error["msg"],
                                "type": error["type"],
                            }
                            for error in exc.errors()
                        ]
                    },
                    status_code=422,
                )
            except AssistantNotFound as exc:
                raise HTTPException(404, str(exc)) from None
            except AssistantAccessError as exc:
                raise HTTPException(403, str(exc)) from None
            except AssistantConfigurationError as exc:
                raise HTTPException(422, str(exc)) from None
            except AssistantConflict as exc:
                raise HTTPException(409, str(exc)) from None
            except CredentialError as exc:
                raise HTTPException(503, str(exc)) from None
            except LLMRateLimitError:
                raise HTTPException(
                    429, "Provider quota or rate limit reached. Retry later."
                ) from None
            except LLMTimeoutError:
                raise HTTPException(
                    504, "The provider connection test timed out."
                ) from None
            except LLMConnectionError:
                raise HTTPException(503, "The provider could not be reached.") from None
            except LLMResponseError as exc:
                if exc.status_code in (408, 504):
                    raise HTTPException(
                        504, "The provider connection timed out."
                    ) from None
                if exc.status_code == 503:
                    raise HTTPException(
                        503, "The provider is temporarily unavailable."
                    ) from None
                if exc.status_code in (401, 403):
                    raise HTTPException(
                        422, "The provider rejected the API key or model access."
                    ) from None
                if exc.status_code in (400, 404):
                    raise HTTPException(
                        422,
                        "The selected model or generation settings are unavailable on this connection.",
                    ) from None
                raise HTTPException(
                    502, "The provider returned an unusable response."
                ) from None
            except IntegrityError:
                raise HTTPException(
                    409, "Configuration changed while saving. Refresh and try again."
                ) from None
            except (SQLAlchemyError, TimeoutError, OSError):
                raise HTTPException(503, self.storage_error_detail) from None

        return safe_handler


class AssistantConfigurationRoute(ConfigurationRoute):
    storage_error_detail = "Assistant configuration storage is temporarily unavailable."


class WidgetConfigurationRoute(ConfigurationRoute):
    # Preserve the widget API's existing error body during the structural move.
    storage_error_detail = "Assistant configuration storage is temporarily unavailable."
