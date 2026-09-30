"""Schemas for document ingestion, upload, and search."""

from datetime import datetime
from typing import Annotated, Literal, Self
from unicodedata import category
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

DocumentIds = Annotated[list[UUID], Field(min_length=1, max_length=20)]

INVALID_FILENAME_CHARACTERS = set('<>:"/\\|?*')
MAX_INGESTION_BATCH_SIZE = 256

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class StrictSchema(BaseModel):
    """Reject fields that are not declared by the schema."""

    model_config = ConfigDict(extra="forbid")


class DocumentUploadMetadata(StrictSchema):
    """Validated metadata supplied with an uploaded PDF."""

    filename: str = Field(min_length=1, max_length=255)
    content_type: Literal["application/pdf"]

    @field_validator("filename", mode="before")
    @classmethod
    def validate_filename(cls, value: object) -> str:
        """Reject blank, oversized, path-like, or unsafe filenames."""

        if not isinstance(value, str):
            raise ValueError("A filename is required.")

        if len(value) > 255:
            raise ValueError("Filename cannot exceed 255 characters.")

        if any(category(character).startswith("C") for character in value):
            raise ValueError("Filename contains control characters.")

        filename = value.strip()

        if not filename:
            raise ValueError("Filename cannot be blank.")

        if (
            filename in {".", ".."}
            or filename.endswith(".")
            or any(
                character in INVALID_FILENAME_CHARACTERS
                for character in filename
            )
        ):
            raise ValueError("Filename contains unsafe characters.")

        stem = filename.split(".", maxsplit=1)[0].rstrip(" ").upper()

        if stem in WINDOWS_RESERVED_NAMES:
            raise ValueError("Filename is reserved by Windows.")

        if not filename.lower().endswith(".pdf"):
            raise ValueError("Filename must end in .pdf.")

        if not filename[:-4].strip():
            raise ValueError("A PDF filename needs a nonempty name.")

        return filename


class DocumentResponse(StrictSchema):
    """Metadata for a stored document."""

    id: UUID
    filename: str
    page_count: int = Field(ge=1)
    status: Literal["pending", "ready", "failed"]
    created_at: datetime


class ChunkResponse(StrictSchema):
    """A stored text chunk with its document source."""

    id: UUID
    document_id: UUID
    filename: str
    page_number: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
    content: NonBlankText


class ChunkInput(StrictSchema):
    """A text chunk produced during PDF extraction."""

    chunk_index: int = Field(ge=0)
    page_number: int = Field(ge=1)
    content: NonBlankText


class IngestionPayload(StrictSchema):
    """Validated batch of chunks produced during ingestion."""

    document_id: UUID
    page_count: int = Field(ge=1)
    chunks: list[ChunkInput] = Field(
        min_length=1,
        max_length=MAX_INGESTION_BATCH_SIZE,
    )

    @model_validator(mode="after")
    def validate_chunks(self) -> Self:
        """Check that indexes are unique and pages are in range."""

        indexes = [chunk.chunk_index for chunk in self.chunks]

        if len(indexes) != len(set(indexes)):
            raise ValueError("Chunk indexes must be unique.")

        if any(
            chunk.page_number > self.page_count
            for chunk in self.chunks
        ):
            raise ValueError("Chunk page exceeds document page count.")

        return self


class DocumentUploadResponse(StrictSchema):
    """Result of uploading a new or previously indexed PDF."""

    document_id: UUID
    filename: str
    page_count: int = Field(ge=1)
    chunk_count: int = Field(ge=1)
    status: Literal["ready"]
    already_existed: bool


class DocumentSearchRequest(StrictSchema):
    """Question, result limit, and optional document selection."""

    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20, strict=True)
    document_ids: DocumentIds | None = None

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: object) -> str:
        """Trim whitespace and reject empty questions."""

        if not isinstance(value, str):
            raise ValueError("Query must be text.")

        query = value.strip()

        if not query:
            raise ValueError("Query cannot be blank.")

        return query


class DocumentChunkResult(StrictSchema):
    """One retrieved passage with its source and cosine distance."""

    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
    content: NonBlankText
    cosine_distance: float = Field(
        ge=0.0,
        le=2.0,
        allow_inf_nan=False,
    )


class DocumentSearchResponse(StrictSchema):
    """Ranked passages returned by document search."""

    query: str
    top_k: int = Field(ge=1, le=20)
    matches: int = Field(ge=0, le=20)
    results: list[DocumentChunkResult]
