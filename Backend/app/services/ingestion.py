import asyncio
import logging
import math
from dataclasses import dataclass
from contextlib import suppress
from uuid import UUID, uuid4
from importlib.metadata import version

from pydantic import ValidationError

from app.providers.base import BaseEmbeddingProvider
from app.providers.documents import PDFExtractionError, validate_pdf_bytes
from app.providers.pdf_process import extract_pdf_isolated
from app.schemas.documents import ChunkInput, DocumentUploadMetadata, IngestionPayload
from app.services.chunking import ChunkingError, chunk_document, TOKENIZER_REVISION
from app.services.document_hash import pdf_sha256
from app.services.document_metadata import extract_document_metadata, ensure_document_metadata, metadata_record
from app.storage.db import Database
from app.storage.documents import (
    ExistingDocument,
    ClaimedDocument,
    claim_document,
    complete_document,
    fail_document,
    find_document_by_hash,
    renew_document_lease,
    abandon_document_claim,
    release_document_claim,
    retain_existing_source,
    DocumentClaimLostError,
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
    expected_document_id: UUID | None = None,
) -> IngestionResult:
    settings = getattr(database, "settings", None)
    try:
        async with asyncio.timeout(getattr(settings, "ingestion_timeout_seconds", 600)):
            return await _ingest_pdf(database=database, embeddings=embeddings, filename=filename,
                                     data=data, lease_seconds=getattr(settings, "ingestion_lease_seconds", 120),
                                     expected_document_id=expected_document_id)
    except TimeoutError as exc:
        raise IngestionProcessingError("Document processing exceeded its deadline; re-upload to retry.") from exc


async def _ingest_pdf(*, database, embeddings, filename, data, lease_seconds, expected_document_id=None):
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
    if expected_document_id is not None and (existing is None or existing.id != expected_document_id):
        raise DocumentClaimLostError("The queued document was removed.")
    if existing is not None and (existing.status == "ready" or (existing.status == "pending" and existing.lease_active)):
        if existing.status == "ready":
            await retain_existing_source(database, digest, data)
            try:
                await ensure_document_metadata(database, embeddings, existing.id)
            except Exception as exc:
                # A historical ready document remains usable during an embedding
                # outage. The idempotent backfill can retry its missing metadata.
                logger.warning("Duplicate metadata backfill deferred (%s)", type(exc).__name__)
        return _existing_result(existing)

    if (
        embeddings.dimensions != EMBEDDING_DIMENSIONS
        or embeddings.space_id != EMBEDDING_SPACE
    ):
        raise IngestionProcessingError(
            "Embedding provider does not match the database schema."
        )

    # Invalid files are rejected before reserving a database row.
    settings = getattr(database, "settings", None)
    logger.info("PDF processing stage=parse document_id=%s", expected_document_id or "new")
    extracted = await extract_pdf_isolated(
        data, timeout_seconds=getattr(settings, "pdf_parse_timeout_seconds", 30),
        memory_mb=getattr(settings, "pdf_parse_memory_mb", 512),
    )
    claimed, heartbeat, attempt_id = None, None, uuid4()
    stage = "claim"
    try:
        claimed = await claim_document(
            database, filename=metadata.filename, content_sha256=digest,
            page_count=extracted.page_count, attempt_id=attempt_id, lease_seconds=lease_seconds,
            original_pdf=data,
            expected_document_id=expected_document_id,
            processing_metadata={
                "pipeline_version": 2, "embedding_space": embeddings.space_id,
                "packages": {name: version(name) for name in ("pypdf", "fastembed", "tokenizers")},
                "chunk_tokens": 350, "overlap_tokens": 40,
                "tokenizer_revision": TOKENIZER_REVISION,
                "embedding_revision": getattr(embeddings, "MODEL_REVISION", None),
                "pages_without_searchable_text": sorted(
                    set(range(1, extracted.page_count + 1)) - {page.page_number for page in extracted.pages}
                ),
            },
        )
        if isinstance(claimed, ExistingDocument):
            return _existing_result(claimed)

        async def keep_lease():
            while True:
                await asyncio.sleep(lease_seconds / 3)
                await renew_document_lease(database, claimed.id, attempt_id, lease_seconds)
        heartbeat = asyncio.create_task(keep_lease())
        # No database connection is held during tokenization or inference.
        stage = "chunking"
        chunks = await asyncio.to_thread(chunk_document, extracted)
        if len(chunks) > MAX_CHUNKS_PER_DOCUMENT:
            raise ChunkingError(
                f"Document exceeds the {MAX_CHUNKS_PER_DOCUMENT}-chunk limit."
            )

        chunk_ids = [uuid4() for _ in chunks]
        stage = "metadata"
        identity = await asyncio.to_thread(extract_document_metadata, claimed.filename, [
            {"id": identifier, "page_number": chunk.page_number, "content": chunk.content}
            for identifier, chunk in zip(chunk_ids, chunks, strict=True)
        ])
        identity_vector = None

        records: list[dict[str, object]] = []
        stage = "embedding"
        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            if expected_document_id is not None:
                # Stop between batches when a queued upload has been deleted.
                try:
                    await renew_document_lease(database, claimed.id, attempt_id, lease_seconds)
                except RuntimeError:
                    raise DocumentClaimLostError("The queued document is no longer owned by this worker.") from None
            logger.info("PDF processing stage=embedding document_id=%s completed_chunks=%d total_chunks=%d",
                        claimed.id, start, len(chunks))
            payload = IngestionPayload(
                document_id=claimed.id, page_count=extracted.page_count,
                chunks=[ChunkInput(
                    chunk_index=chunk.chunk_index, page_number=chunk.page_number,
                    content=chunk.content,
                ) for chunk in chunks[start:start + EMBED_BATCH_SIZE]],
            )
            texts = [chunk.content for chunk in payload.chunks]
            include_summary = start + EMBED_BATCH_SIZE >= len(chunks) and len(texts) < EMBED_BATCH_SIZE
            if include_summary:
                texts.append(identity.summary)
            vectors = await embeddings.embed_documents(texts)
            if len(vectors) != len(texts):
                raise IngestionProcessingError(
                    "Embedding count does not match the chunk count."
                )

            if include_summary:
                identity_vector = vectors[-1]
                vectors = vectors[:-1]
            for offset, (chunk, vector) in enumerate(zip(payload.chunks, vectors, strict=True)):
                if (
                    len(vector) != EMBEDDING_DIMENSIONS
                    or not all(math.isfinite(value) for value in vector)
                    or not math.isclose(math.hypot(*vector), 1.0, rel_tol=1e-5)
                ):
                    raise IngestionProcessingError(
                        "Expected finite, normalized 384-dimensional embeddings."
                    )
                records.append({
                    "id": chunk_ids[start + offset], "document_id": claimed.id,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                    "content": chunk.content,
                    "embedding_space": embeddings.space_id,
                    "embedding": vector,
                })
        if identity_vector is None:
            summary_vectors = await embeddings.embed_documents([identity.summary])
            if len(summary_vectors) != 1:
                raise IngestionProcessingError("Metadata embedding count mismatch.")
            identity_vector = summary_vectors[0]
        identity_record = metadata_record(identity, identity_vector)
        if heartbeat.done():
            heartbeat.result()
        stage = "publish"
        await complete_document(database, claimed.id, records, attempt_id=attempt_id,
                                document_metadata=identity_record)
    except (Exception, asyncio.CancelledError) as exc:
        if not isinstance(exc, (asyncio.CancelledError, DocumentClaimLostError)):
            logger.warning("PDF processing failed stage=%s cause=%s document_id=%s",
                           stage, type(exc).__name__, getattr(claimed, "id", expected_document_id))
        try:
            # Preserve retryability when a request is cancelled during inference.
            if isinstance(exc, asyncio.CancelledError):
                await asyncio.shield(release_document_claim(database, digest, attempt_id))
            elif isinstance(claimed, ClaimedDocument):
                await asyncio.shield(fail_document(database, claimed.id, attempt_id=attempt_id))
            else:
                await asyncio.shield(abandon_document_claim(database, digest, attempt_id))
        except (Exception, asyncio.CancelledError) as cleanup_error:
            logger.error(
                "Could not mark document %s failed (%s)",
                getattr(claimed, "id", "unconfirmed"), type(cleanup_error).__name__,
            )
        if isinstance(exc, (
            ChunkingError, IngestionProcessingError, DocumentClaimLostError, asyncio.CancelledError,
        )):
            raise
        raise IngestionProcessingError(
            "Document processing failed; please retry."
        ) from exc
    finally:
        if heartbeat is not None:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await heartbeat

    return IngestionResult(
        document_id=claimed.id, filename=claimed.filename,
        page_count=extracted.page_count, chunk_count=len(records),
        status="ready", already_existed=claimed.already_existed,
    )
