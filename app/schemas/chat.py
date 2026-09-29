"""Pydantic V2 schemas for the RAG chat API."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


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


class ChatRequest(StrictSchema):
    """Question and maximum number of passages to retrieve."""

    question: QuestionText
    top_k: int = Field(default=5, ge=1, le=20, strict=True)


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