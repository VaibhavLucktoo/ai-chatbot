"""Database operations for document deduplication and hybrid search."""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select, union_all, update, or_, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.schemas.documents import MAX_INGESTION_BATCH_SIZE
from app.storage.db import Database
from app.storage.models import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_SPACE,
    Document,
    DocumentChunk,
    DocumentMetadata,
)

RRF_K = 60


def _lexical_query(query: str):
    """Match any question term; PostgreSQL handles English stems/stop words.

    Quoted word tokens cannot inject web-search operators. The whole query is
    passed as a bound SQL parameter, never interpolated into SQL text.
    """
    terms = re.findall(r"\w+", query)
    return func.websearch_to_tsquery(
        "english", " OR ".join(f'"{term}"' for term in terms),
    )


def _rrf_scores(vector_candidates, lexical_candidates):
    """Sum reciprocal one-based ranks, retaining candidates from either list."""
    candidates = union_all(
        select(vector_candidates.c.chunk_id, vector_candidates.c.rank),
        select(lexical_candidates.c.chunk_id, lexical_candidates.c.rank),
    ).subquery("candidates")
    return (
        select(
            candidates.c.chunk_id,
            func.sum(1.0 / (RRF_K + candidates.c.rank)).label("rrf_score"),
        )
        .group_by(candidates.c.chunk_id)
        .subquery("fused")
    )


def _hybrid_search(statement, distance, query: str, top_k: int, *, include_document_identity: bool = False):
    """Build both candidate lists and fuse ranks in one database snapshot."""
    candidate_k = min(max(top_k * 3, 10), 50)
    vector_order = (distance.asc(), DocumentChunk.id.asc())
    vector_candidates = (
        statement.with_only_columns(
            DocumentChunk.id.label("chunk_id"),
            distance,
        )
        .order_by(*vector_order).limit(candidate_k).subquery("semantic_limited")
    )
    vector_candidates = select(
        vector_candidates.c.chunk_id,
        func.row_number().over(order_by=(vector_candidates.c.cosine_distance,
                                       vector_candidates.c.chunk_id)).label("rank"),
    ).subquery("semantic")
    text_vector = func.to_tsvector(literal_column("'english'::regconfig"), DocumentChunk.content)
    text_query = _lexical_query(query)
    lexical_order = (func.ts_rank(text_vector, text_query).desc(), DocumentChunk.id.asc())
    lexical_candidates = (
        statement.with_only_columns(
            DocumentChunk.id.label("chunk_id"),
            func.row_number().over(order_by=lexical_order).label("rank"),
        )
        .where(text_vector.bool_op("@@")(text_query))
        .order_by(*lexical_order).limit(candidate_k).subquery("lexical")
    )
    fused = _rrf_scores(vector_candidates, lexical_candidates)
    if include_document_identity:
        # Use the same ready/active/model/authorization filters as BOTH ranked
        # lists. This bounded candidate is included even outside the rank pools.
        opening = (
            statement.with_only_columns(DocumentChunk.id.label("chunk_id"))
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index, DocumentChunk.id)
            .limit(1).subquery("document_identity")
        )
        ranked = (
            statement.outerjoin(fused, DocumentChunk.id == fused.c.chunk_id)
            .outerjoin(opening, DocumentChunk.id == opening.c.chunk_id)
            .where(or_(fused.c.chunk_id.is_not(None), opening.c.chunk_id.is_not(None)))
            .order_by(opening.c.chunk_id.is_not(None).desc(),
                      fused.c.rrf_score.desc().nulls_last(), DocumentChunk.id.asc())
        )
    else:
        ranked = statement.join(fused, DocumentChunk.id == fused.c.chunk_id).order_by(
            fused.c.rrf_score.desc(), DocumentChunk.id.asc())
    return (
        ranked
        .limit(top_k)
        .add_columns(
            func.tsvector_to_array(func.to_tsvector("english", query)).label("query_lexemes"),
            func.tsvector_to_array(text_vector).label("content_lexemes"),
        )
    )


@dataclass(frozen=True, slots=True)
class ExistingDocument:
    """Previously stored document found by its content hash."""

    id: UUID
    filename: str
    page_count: int
    chunk_count: int
    status: str
    lease_active: bool = False


@dataclass(frozen=True, slots=True)
class ClaimedDocument:
    """Document reserved by this ingestion attempt."""

    id: UUID
    filename: str
    already_existed: bool
    attempt_id: UUID


@dataclass(frozen=True, slots=True)
class StoredChunkResult:
    """One database search result."""

    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int
    chunk_index: int
    content: str
    cosine_distance: float
    # Internal evidence metadata; public API schemas keep their existing fields.
    # Exclude metadata from equality so vector/hybrid diagnostics stay comparable.
    query_lexemes: tuple[str, ...] = field(default=(), compare=False, repr=False)
    matched_lexemes: tuple[str, ...] = field(default=(), compare=False, repr=False)


async def find_document_by_hash(
    database: Database,
    content_sha256: str,
) -> ExistingDocument | None:
    """Find a committed document, including documents with no chunks."""

    async with database.transaction() as connection:
        return await _find_document(connection, content_sha256)


async def retain_existing_source(database: Database, digest: str, data: bytes):
    """Backfill an immutable legacy source without claiming new provenance."""
    async with database.transaction() as connection:
        await connection.execute(update(Document).where(
            Document.content_sha256 == digest, Document.status == "ready", Document.original_pdf.is_(None),
        ).values(original_pdf=data))


async def _find_document(
    connection: AsyncConnection,
    content_sha256: str,
) -> ExistingDocument | None:
    statement = (
        select(
            Document.id,
            Document.filename,
            Document.page_count,
            Document.status,
            (Document.lease_expires_at > func.now()).label("lease_active"),
            func.count(DocumentChunk.id).label("chunk_count"),
        )
        .outerjoin(
            DocumentChunk,
            DocumentChunk.document_id == Document.id,
        )
        .where(Document.content_sha256 == content_sha256)
        .group_by(
            Document.id,
            Document.filename,
            Document.page_count,
            Document.status,
            Document.lease_expires_at,
        )
    )

    row = (await connection.execute(statement)).mappings().one_or_none()

    if row is None:
        return None

    return ExistingDocument(
        id=row["id"],
        filename=row["filename"],
        page_count=row["page_count"],
        chunk_count=int(row["chunk_count"]),
        status=row["status"],
        lease_active=bool(row["lease_active"]),
    )


async def claim_document(
    database: Database,
    *,
    filename: str,
    content_sha256: str,
    page_count: int,
    attempt_id: UUID | None = None,
    lease_seconds: int = 120,
    original_pdf: bytes | None = None,
    processing_metadata: dict | None = None,
) -> ClaimedDocument | ExistingDocument:
    """Allow only one request to create or retry a given PDF."""
    attempt_id = attempt_id or uuid4()
    async with database.transaction() as connection:
        created = (
            await connection.execute(
                pg_insert(Document.__table__)
                .values(
                    id=uuid4(),
                    filename=filename,
                    content_sha256=content_sha256,
                    page_count=page_count,
                    status="pending",
                    attempt_id=attempt_id,
                    lease_expires_at=func.now() + timedelta(seconds=lease_seconds),
                    original_pdf=original_pdf,
                    processing_metadata=processing_metadata,
                    ingestion_attempts=1,
                )
                .on_conflict_do_nothing(
                    index_elements=[Document.content_sha256],
                )
                .returning(Document.id, Document.filename)
            )
        ).one_or_none()

        if created is not None:
            return ClaimedDocument(created.id, created.filename, False, attempt_id)

        # PostgreSQL rechecks this condition under its row lock.
        retried = (
            await connection.execute(
                update(Document)
                .where(
                    Document.content_sha256 == content_sha256,
                    or_(Document.status == "failed", (
                        (Document.status == "pending") & or_(
                            Document.lease_expires_at.is_(None), Document.lease_expires_at <= func.now(),
                        )
                    )),
                )
                .values(status="pending", attempt_id=attempt_id, page_count=page_count,
                        original_pdf=original_pdf, processing_metadata=processing_metadata,
                        ingestion_attempts=Document.ingestion_attempts + 1,
                        lease_expires_at=func.now() + timedelta(seconds=lease_seconds))
                .returning(Document.id, Document.filename)
            )
        ).one_or_none()

        if retried is not None:
            await connection.execute(delete(DocumentMetadata).where(DocumentMetadata.document_id == retried.id))
            await connection.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == retried.id,
                )
            )
            return ClaimedDocument(retried.id, retried.filename, True, attempt_id)

        existing = await _find_document(connection, content_sha256)
        if existing is None:
            raise RuntimeError("The document was removed during ingestion; retry.")
        return existing


async def complete_document(
    database: Database,
    document_id: UUID,
    records: list[dict[str, object]],
    *, attempt_id: UUID, document_metadata: dict | None = None,
) -> None:
    """Commit every chunk and the ready status in one transaction."""
    if not records:
        raise ValueError("A ready document must contain chunks.")

    async with database.transaction() as connection:
        result = await connection.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "pending",
                   Document.attempt_id == attempt_id, Document.lease_expires_at > func.now())
            .values(status="ready", lease_expires_at=None, attempt_id=None)
        )
        if result.rowcount != 1:
            raise RuntimeError("The document is no longer pending.")

        for start in range(0, len(records), MAX_INGESTION_BATCH_SIZE):
            await connection.execute(
                insert(DocumentChunk.__table__),
                records[start:start + MAX_INGESTION_BATCH_SIZE],
            )
        if document_metadata is not None:
            await connection.execute(insert(DocumentMetadata).values(document_id=document_id, **document_metadata))


async def fail_document(database: Database, document_id: UUID, *, attempt_id: UUID) -> None:
    """Clear partial chunks and make a pending document retryable."""
    async with database.transaction() as connection:
        result = await connection.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "pending", Document.attempt_id == attempt_id)
            .values(status="failed", lease_expires_at=None, attempt_id=None)
        )
        if result.rowcount == 1:
            await connection.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == document_id,
                )
            )


async def renew_document_lease(database: Database, document_id: UUID, attempt_id: UUID, lease_seconds: int):
    async with database.transaction() as connection:
        result = await connection.execute(update(Document).where(
            Document.id == document_id, Document.status == "pending", Document.attempt_id == attempt_id,
            Document.lease_expires_at > func.now(),
        ).values(lease_expires_at=func.now() + timedelta(seconds=lease_seconds)))
        if result.rowcount != 1:
            raise RuntimeError("Ingestion ownership expired or changed.")


async def abandon_document_claim(database: Database, digest: str, attempt_id: UUID):
    """Resolve a cancelled claim whose committed ID was not returned."""
    async with database.transaction() as connection:
        await connection.execute(update(Document).where(
            Document.content_sha256 == digest, Document.status == "pending", Document.attempt_id == attempt_id,
        ).values(status="failed", lease_expires_at=None, attempt_id=None))


async def release_document_claim(database: Database, digest: str, attempt_id: UUID):
    """Leave cancelled durable work pending and immediately recoverable."""
    async with database.transaction() as connection:
        await connection.execute(update(Document).where(
            Document.content_sha256 == digest, Document.status == "pending", Document.attempt_id == attempt_id,
        ).values(lease_expires_at=func.now()))


async def search_similar_chunks(
    database: Database | AsyncSession,
    query_vector: Sequence[float],
    top_k: int = 5,
    *,
    document_ids: Sequence[UUID] | None = None,
    query: str | None = None,
    allowed_document_ids: Sequence[UUID] | None = None,
    include_document_identity: bool = False,
) -> list[StoredChunkResult]:
    """Return up to top_k compatible ready chunks, with original cosine distances.

    Supplying query enables hybrid RRF ranking. Omitting it preserves the exact
    vector-only storage operation for existing callers and diagnostics.
    """

    if type(top_k) is not int or not 1 <= top_k <= 20:
        raise ValueError("top_k must be an integer between 1 and 20.")

    selected_documents = validate_document_ids(document_ids)
    if query is not None and (not isinstance(query, str) or not query.strip()):
        raise ValueError("Query must be nonblank text when supplied.")

    if len(query_vector) != EMBEDDING_DIMENSIONS:
        raise ValueError("Query vector has incorrect dimensions.")

    try:
        vector = [float(value) for value in query_vector]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Query vector must contain numbers.") from exc

    if not all(math.isfinite(value) for value in vector):
        raise ValueError("Query vector must contain finite numbers.")

    if not any(value != 0.0 for value in vector):
        raise ValueError("Cosine search requires a nonzero vector.")

    distance = DocumentChunk.embedding.cosine_distance(vector).label(
        "cosine_distance"
    )

    statement = (
        select(
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.document_id,
            Document.filename,
            DocumentChunk.page_number,
            DocumentChunk.chunk_index,
            DocumentChunk.content,
            distance,
        )
        .select_from(DocumentChunk)
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .where(
            Document.status == "ready", Document.active.is_(True),
            DocumentChunk.embedding_space == EMBEDDING_SPACE,
            DocumentChunk.embedding.is_not(None),
        )
    )

    if selected_documents is not None:
        statement = statement.where(
            DocumentChunk.document_id.in_(selected_documents)
        )

    if allowed_document_ids is not None:
        # Internal authorization scope is independent of the user's <=20-ID picker.
        # IN [] deliberately yields no results; an empty assignment never broadens.
        statement = statement.where(DocumentChunk.document_id.in_(allowed_document_ids))

    if query is None:
        statement = statement.order_by(distance.asc(), DocumentChunk.id.asc()).limit(top_k)
    else:
        statement = _hybrid_search(statement, distance, query, top_k,
                                   include_document_identity=include_document_identity)

    if isinstance(database, AsyncSession):
        # The caller owns the session and its transaction. Retrieval must not
        # flush unrelated changes, commit, roll back, or close that session.
        with database.no_autoflush:
            rows = (await database.execute(statement)).mappings().all()
    else:
        async with database.transaction() as connection:
            rows = (
                await connection.execute(statement)
            ).mappings().all()

    results: list[StoredChunkResult] = []

    for row in rows:
        raw_distance = float(row["cosine_distance"])

        if not math.isfinite(raw_distance):
            raise RuntimeError("Stored vector produced an invalid distance.")

        # Allow only negligible floating-point drift outside [0, 2].
        if raw_distance < -1e-6 or raw_distance > 2.0 + 1e-6:
            raise RuntimeError("Stored vector produced an invalid distance.")

        results.append(
            StoredChunkResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                filename=row["filename"],
                page_number=row["page_number"],
                chunk_index=row["chunk_index"],
                content=row["content"],
                cosine_distance=max(0.0, min(2.0, raw_distance)),
                query_lexemes=tuple(row.get("query_lexemes", ())),
                matched_lexemes=tuple(sorted(
                    set(row.get("query_lexemes", ()))
                    & set(row.get("content_lexemes", ()))
                )),
            )
        )

    return results


def validate_document_ids(
    document_ids: Sequence[UUID] | None,
) -> tuple[UUID, ...] | None:
    """Validate an optional filter without interpreting an empty list as all."""
    if document_ids is None:
        return None
    if (
        not isinstance(document_ids, Sequence)
        or isinstance(document_ids, (str, bytes))
        or not 1 <= len(document_ids) <= 20
        or not all(isinstance(document_id, UUID) for document_id in document_ids)
    ):
        raise ValueError("document_ids must contain between 1 and 20 UUIDs.")
    return tuple(document_ids)
