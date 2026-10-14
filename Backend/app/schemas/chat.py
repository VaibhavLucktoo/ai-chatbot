"""Pydantic V2 schemas for the RAG chat API."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.documents import DocumentIds


QuestionText = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=500,
    ),
]


class StrictSchema(BaseModel):
    """Reject undeclared fields."""

    model_config = ConfigDict(extra="forbid")


class DocumentChoice(StrictSchema):
    """Display a filename with its unambiguous selection ID."""

    document_id: UUID
    filename: str


class ClarificationResponse(StrictSchema):
    """Ask the client to select documents and resend the original request."""

    status: Literal["clarification_required"] = "clarification_required"
    question: str
    original_question: str
    top_k: int
    documents: list[DocumentChoice]


class ChatRequest(StrictSchema):
    """Question, result limit, optional assistant and narrowed document selection."""

    question: QuestionText
    top_k: int = Field(default=5, ge=1, le=20, strict=True)
    document_ids: DocumentIds | None = None
    conversation_id: UUID | None = None
    assistant_id: UUID | None = None


class ChatSource(StrictSchema):
    """Source identifiers and page metadata for a supporting passage."""

    document_id: UUID
    chunk_id: UUID
    filename: str = Field(strict=True)
    page_number: int = Field(ge=1, strict=True)


class ChatResponse(StrictSchema):
    """Generated answer and its supporting sources."""

    answer: str = Field(strict=True)
    sources: list[ChatSource] = Field(strict=True)
