"""Widget administration and the deliberately narrow visitor contract."""
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from app.schemas.chat import QuestionText
from app.schemas.documents import DocumentIds


def website_origin(value: str) -> str:
    value = value.strip()
    try:
        url = urlsplit(value)
        port = url.port
        host = url.hostname
        if (url.scheme not in {"http", "https"} or not host or url.username is not None
                or url.password is not None or url.path not in {"", "/"} or url.query or url.fragment
                or any(c.isspace() for c in value) or "\\" in value or "*" in value):
            raise ValueError()
        if url.scheme == "http" and host not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError()
        host = host.encode("idna").decode("ascii").lower()
        # CSP sources must never contain delimiters or invalid host characters.
        import re
        if host != "::1" and not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
            raise ValueError()
        host = "[::1]" if host == "::1" else host
        suffix = f":{port}" if port is not None and port != (443 if url.scheme == "https" else 80) else ""
        return f"{url.scheme}://{host}{suffix}"
    except (ValueError, UnicodeError):
        raise ValueError("Use an exact HTTPS website origin, such as https://example.com; HTTP is allowed only for localhost.") from None


class WidgetSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class WidgetWrite(WidgetSchema):
    enabled: bool = False
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] = "Document Assistant"
    greeting: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)] = "Hello! What would you like to know?"
    color: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")
    position: Literal["left", "right"] = "right"
    allowed_origins: list[str] = Field(default_factory=list, max_length=20)
    requests_per_minute: int = Field(default=20, ge=1, le=120, strict=True)
    requests_per_day: int = Field(default=500, ge=1, le=10000, strict=True)

    @field_validator("allowed_origins")
    @classmethod
    def origins(cls, values):
        return list(dict.fromkeys(website_origin(value) for value in values))

class WidgetResponse(WidgetWrite):
    id: UUID
    assistant_id: UUID
    revision: int
    public_origin: str
    public_access_enabled: bool
    requests_today: int = 0


class VisitorStart(WidgetSchema):
    parent_origin: str = Field(max_length=300)
    _origin = field_validator("parent_origin")(website_origin)


class VisitorChat(WidgetSchema):
    question: QuestionText
    document_ids: DocumentIds | None = None


class VisitorSession(WidgetSchema):
    session_id: UUID
    token: str
    expires_at: str


class WidgetPassageResponse(WidgetSchema):
    id: UUID
    document_id: UUID
    filename: str
    page_number: int
    chunk_index: int
    # Return exactly the stored text; do not strip whitespace during serialization.
    content: str
