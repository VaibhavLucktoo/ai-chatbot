"""Database operations for document deduplication and hybrid search."""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select, union_all, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.schemas.documents import MAX_INGESTION_BATCH_SIZE
from app.storage.db import Database
from app.storage.models import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_SPACE,
    Document,
    DocumentChunk,
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


def _hybrid_search(statement, distance, query: str, top_k: int):
    """Build both candidate lists and fuse ranks in one database snapshot."""
    candidate_k = min(max(top_k * 3, 10), 50)
    vector_order = (distance.asc(), DocumentChunk.id.asc())
    vector_candidates = (
        statement.with_only_columns(
            DocumentChunk.id.label("chunk_id"),
            func.row_number().over(order_by=vector_order).label("rank"),
        )
        .order_by(*vector_order).limit(candidate_k).subquery("semantic")
    )
    text_vector = func.to_tsvector("english", DocumentChunk.content)
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
    return (
        statement.join(fused, DocumentChunk.id == fused.c.chunk_id)
        .order_by(fused.c.rrf_score.desc(), DocumentChunk.id.asc())
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


@dataclass(frozen=True, slots=True)
class ClaimedDocument:
    """Document reserved by this ingestion attempt."""

    id: UUID
    filename: str
    already_existed: bool


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
    )


async def claim_document(
    database: Database,
    *,
    filename: str,
    content_sha256: str,
    page_count: int,
) -> ClaimedDocument | ExistingDocument:
    """Allow only one request to create or retry a given PDF."""
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
                )
                .on_conflict_do_nothing(
                    index_elements=[Document.content_sha256],
                )
                .returning(Document.id, Document.filename)
            )
        ).one_or_none()

        if created is not None:
            return ClaimedDocument(created.id, created.filename, False)

        # PostgreSQL rechecks this condition under its row lock.
        retried = (
            await connection.execute(
                update(Document)
                .where(
                    Document.content_sha256 == content_sha256,
                    Document.status == "failed",
                )
                .values(status="pending")
                .returning(Document.id, Document.filename)
            )
        ).one_or_none()

        if retried is not None:
            await connection.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == retried.id,
                )
            )
            return ClaimedDocument(retried.id, retried.filename, True)

        existing = await _find_document(connection, content_sha256)
        if existing is None:
            raise RuntimeError("The document was removed during ingestion; retry.")
        return existing


async def complete_document(
    database: Database,
    document_id: UUID,
    records: list[dict[str, object]],
) -> None:
    """Commit every chunk and the ready status in one transaction."""
    if not records:
        raise ValueError("A ready document must contain chunks.")

    async with database.transaction() as connection:
        result = await connection.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "pending")
            .values(status="ready")
        )
        if result.rowcount != 1:
            raise RuntimeError("The document is no longer pending.")

        for start in range(0, len(records), MAX_INGESTION_BATCH_SIZE):
            await connection.execute(
                insert(DocumentChunk.__table__),
                records[start:start + MAX_INGESTION_BATCH_SIZE],
            )


async def fail_document(database: Database, document_id: UUID) -> None:
    """Clear partial chunks and make a pending document retryable."""
    async with database.transaction() as connection:
        result = await connection.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "pending")
            .values(status="failed")
        )
        if result.rowcount == 1:
            await connection.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == document_id,
                )
            )


async def search_similar_chunks(
    database: Database | AsyncSession,
    query_vector: Sequence[float],
    top_k: int = 5,
    *,
    document_ids: Sequence[UUID] | None = None,
    query: str | None = None,
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
            Document.status == "ready",
            DocumentChunk.embedding_space == EMBEDDING_SPACE,
            DocumentChunk.embedding.is_not(None),
        )
    )

    if selected_documents is not None:
        statement = statement.where(
            DocumentChunk.document_id.in_(selected_documents)
        )

    if query is None:
        statement = statement.order_by(distance.asc(), DocumentChunk.id.asc()).limit(top_k)
    else:
        statement = _hybrid_search(statement, distance, query, top_k)

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
