import asyncio
import logging
import math
from dataclasses import dataclass
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.providers.base import BaseEmbeddingProvider
from app.providers.documents import PDFExtractionError, extract_pdf, validate_pdf_bytes
from app.schemas.documents import ChunkInput, DocumentUploadMetadata, IngestionPayload
from app.services.chunking import ChunkingError, chunk_document
from app.services.document_hash import pdf_sha256
from app.storage.db import Database
from app.storage.documents import (
    ExistingDocument,
    claim_document,
    complete_document,
    fail_document,
    find_document_by_hash,
)
from app.storage.models import EMBEDDING_DIMENSIONS, EMBEDDING_SPACE

logger = logging.getLogger(__name__)
EMBED_BATCH_SIZE = 32
MAX_CHUNKS_PER_DOCUMENT = 1000


class IngestionProcessingError(RuntimeError):
    """A processing dependency failed; the upload can be retried."""


@dataclass(frozen=True, slots=True)
class IngestionResult:
    document_id: UUID
    filename: str
    page_count: int
    chunk_count: int
    status: str
    already_existed: bool


def _existing_result(document: ExistingDocument) -> IngestionResult:
    return IngestionResult(
        document_id=document.id,
        filename=document.filename,
        page_count=document.page_count,
        chunk_count=document.chunk_count,
        status=document.status,
        already_existed=True,
    )


async def ingest_pdf(
    *, database: Database, embeddings: BaseEmbeddingProvider,
    filename: str, data: bytes,
) -> IngestionResult:
    """Claim a PDF, embed it, and publish its chunks atomically."""
    try:
        metadata = DocumentUploadMetadata(
            filename=filename, content_type="application/pdf",
        )
    except ValidationError as exc:
        raise PDFExtractionError(
            "Provide a path-safe .pdf filename of at most 255 characters."
        ) from exc
    validate_pdf_bytes(data)
    digest = pdf_sha256(data)
    existing = await find_document_by_hash(database, digest)
    if existing is not None and existing.status != "failed":
        return _existing_result(existing)

    if (
        embeddings.dimensions != EMBEDDING_DIMENSIONS
        or embeddings.space_id != EMBEDDING_SPACE
    ):
        raise IngestionProcessingError(
            "Embedding provider does not match the database schema."
        )

    # Invalid files are rejected before reserving a database row.
    extracted = await asyncio.to_thread(extract_pdf, data)
    claimed = await claim_document(
        database, filename=metadata.filename, content_sha256=digest,
        page_count=extracted.page_count,
    )
    if isinstance(claimed, ExistingDocument):
        return _existing_result(claimed)

    try:
        # No database connection is held during tokenization or inference.
        chunks = await asyncio.to_thread(chunk_document, extracted)
        if len(chunks) > MAX_CHUNKS_PER_DOCUMENT:
            raise ChunkingError(
                f"Document exceeds the {MAX_CHUNKS_PER_DOCUMENT}-chunk limit."
            )

        records: list[dict[str, object]] = []
        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            payload = IngestionPayload(
                document_id=claimed.id, page_count=extracted.page_count,
                chunks=[ChunkInput(
                    chunk_index=chunk.chunk_index, page_number=chunk.page_number,
                    content=chunk.content,
                ) for chunk in chunks[start:start + EMBED_BATCH_SIZE]],
            )
            vectors = await embeddings.embed_documents(
                [chunk.content for chunk in payload.chunks]
            )
            if len(vectors) != len(payload.chunks):
                raise IngestionProcessingError(
                    "Embedding count does not match the chunk count."
                )

            for chunk, vector in zip(payload.chunks, vectors, strict=True):
                if (
                    len(vector) != EMBEDDING_DIMENSIONS
                    or not all(math.isfinite(value) for value in vector)
                    or not math.isclose(math.hypot(*vector), 1.0, rel_tol=1e-5)
                ):
                    raise IngestionProcessingError(
                        "Expected finite, normalized 384-dimensional embeddings."
                    )
                records.append({
                    "id": uuid4(), "document_id": claimed.id,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                    "content": chunk.content,
                    "embedding_space": embeddings.space_id,
                    "embedding": vector,
                })
        await complete_document(database, claimed.id, records)
    except (Exception, asyncio.CancelledError) as exc:
        try:
            # Preserve retryability when a request is cancelled during inference.
            await asyncio.shield(fail_document(database, claimed.id))
        except (Exception, asyncio.CancelledError) as cleanup_error:
            logger.error(
                "Could not mark document %s failed (%s)",
                claimed.id, type(cleanup_error).__name__,
            )
        if isinstance(exc, (
            ChunkingError, IngestionProcessingError, asyncio.CancelledError,
        )):
            raise
        raise IngestionProcessingError(
            "Document processing failed; please retry."
        ) from exc

    return IngestionResult(
        document_id=claimed.id, filename=claimed.filename,
        page_count=extracted.page_count, chunk_count=len(records),
        status="ready", already_existed=claimed.already_existed,
    )
