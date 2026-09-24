from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonBlankText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentUploadMetadata(StrictSchema):
    filename: str = Field(min_length=1, max_length=255)
    content_type: Literal["application/pdf"] = "application/pdf"

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        value = value.strip()

        if not value or any(char in value for char in ("/", "\\", "\x00")):
            raise ValueError("Provide a filename without a directory path.")

        if not value.lower().endswith(".pdf"):
            raise ValueError("Only PDF filenames are supported.")

        return value


class DocumentResponse(StrictSchema):
    id: UUID
    filename: str
    page_count: int = Field(ge=1)
    status: Literal["pending", "ready", "failed"]
    created_at: datetime


class ChunkResponse(StrictSchema):
    id: UUID
    document_id: UUID
    filename: str
    page_number: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
    content: NonBlankText


class ChunkInput(StrictSchema):
    chunk_index: int = Field(ge=0)
    page_number: int = Field(ge=1)
    content: NonBlankText


class IngestionPayload(StrictSchema):
    """Internal payload produced by trusted PDF extraction code."""

    document_id: UUID
    page_count: int = Field(ge=1)
    chunks: list[ChunkInput] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_chunks(self) -> "IngestionPayload":
        positions = [chunk.chunk_index for chunk in self.chunks]

        if len(positions) != len(set(positions)):
            raise ValueError("Chunk indexes must be unique within a batch.")

        if any(chunk.page_number > self.page_count for chunk in self.chunks):
            raise ValueError("Chunk page exceeds the document page count.")

        return self