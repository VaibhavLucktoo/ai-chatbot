"""Metadata snapshots and fenced backfill publication."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.schemas.document_metadata import METADATA_VERSION, DocumentFact, verified_chunk_facts
from pydantic import ValidationError
from app.storage.models import Document, DocumentChunk, DocumentMetadata


async def metadata_snapshot(database, document_id):
    """Read one bounded ready document; never retain a connection for inference."""
    async with database.transaction() as connection:
        row = (await connection.execute(select(
            Document.filename, Document.content_sha256, DocumentMetadata.version,
        ).outerjoin(DocumentMetadata, DocumentMetadata.document_id == Document.id).where(
            Document.id == document_id, Document.status == "ready",
        ))).one_or_none()
        if row is None or (row.version is not None and row.version >= METADATA_VERSION):
            return None
        chunks = (await connection.execute(select(
            DocumentChunk.id, DocumentChunk.page_number, DocumentChunk.content,
        ).where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index))).mappings().all()
        return row.filename, row.content_sha256, [dict(chunk) for chunk in chunks]


async def publish_metadata_backfill(database, document_id, digest, chunks, metadata):
    """Do not publish for a deleted/replaced document or overwrite a newer version."""
    async with database.transaction() as connection:
        found = await connection.scalar(select(Document.id).where(
            Document.id == document_id, Document.status == "ready", Document.content_sha256 == digest,
        ).with_for_update())
        if found is None:
            return False
        current = (await connection.execute(select(DocumentChunk.id).where(
            DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index))).scalars().all()
        if list(current) != [chunk["id"] for chunk in chunks]:
            return False
        statement = insert(DocumentMetadata).values(document_id=document_id, **metadata)
        result = await connection.execute(statement.on_conflict_do_update(
            index_elements=[DocumentMetadata.document_id], set_=metadata,
            where=DocumentMetadata.version < metadata["version"],
        ).returning(DocumentMetadata.document_id))
        return result.scalar_one_or_none() is not None


async def missing_metadata_ids(database, *, after=None, limit=20):
    statement = select(Document.id).outerjoin(
        DocumentMetadata, DocumentMetadata.document_id == Document.id,
    ).where(Document.status == "ready",
            (DocumentMetadata.version.is_(None)) | (DocumentMetadata.version < METADATA_VERSION))
    if after is not None:
        statement = statement.where(Document.id > after)
    async with database.transaction() as connection:
        return list((await connection.execute(statement.order_by(Document.id).limit(limit))).scalars())


async def metadata_evidence_chunks(connection, query_vector, fields, *, document_ids, allowed_document_ids, limit):
    """Fetch structured facts directly, ranked by field and document summary vector.

    Return original passages and verified annotations, never synthetic citations.
    Both metadata candidates and source passages enforce the same access scope.
    """
    from app.storage.models import EMBEDDING_SPACE

    metadata_query = select(DocumentMetadata.document_id, DocumentMetadata.facts).join(
        Document, Document.id == DocumentMetadata.document_id,
    ).where(Document.status == "ready", Document.active.is_(True),
            DocumentMetadata.version == METADATA_VERSION, DocumentMetadata.embedding_space == EMBEDDING_SPACE)
    source_query = select(
        DocumentChunk.id.label("chunk_id"), DocumentChunk.document_id, Document.filename,
        DocumentChunk.page_number, DocumentChunk.chunk_index, DocumentChunk.content,
        DocumentChunk.embedding.cosine_distance(query_vector).label("cosine_distance"),
    ).join(Document, Document.id == DocumentChunk.document_id).where(
        Document.status == "ready", Document.active.is_(True),
        DocumentChunk.embedding_space == EMBEDDING_SPACE, DocumentChunk.embedding.is_not(None),
    )
    for scope in (document_ids, allowed_document_ids):
        if scope is not None:
            metadata_query = metadata_query.where(DocumentMetadata.document_id.in_(scope))
            source_query = source_query.where(DocumentChunk.document_id.in_(scope))
    rows = (await connection.execute(metadata_query.order_by(
        DocumentMetadata.embedding.cosine_distance(query_vector), DocumentMetadata.document_id,
    ).limit(10))).mappings().all()
    candidates = []
    for rank, row in enumerate(rows):
        for item in row["facts"][:128]:
            try:
                fact = DocumentFact.model_validate(item)
            except (ValidationError, TypeError, ValueError):
                continue
            if fact.field in fields:
                candidates.append((fields.index(fact.field), rank, row["document_id"], fact))
    candidates.sort(key=lambda item: (item[0], item[1], item[3].page_number, str(item[3].chunk_id)))
    if not candidates:
        return []
    # The document index is bounded to ten documents and 128 facts per document.
    identifiers = {item[3].chunk_id for item in candidates}
    sources = (await connection.execute(source_query.where(DocumentChunk.id.in_(identifiers)))).mappings().all()
    source_by_id = {row["chunk_id"]: dict(row) for row in sources}
    matched = {}
    for _, _, document_id, fact in candidates:
        row = source_by_id.get(fact.chunk_id)
        if row is None or row["document_id"] != document_id:
            continue
        verified = verified_chunk_facts({**row, "metadata_evidence": [fact.model_dump(mode="json")]})
        if verified:
            matched.setdefault(fact.chunk_id, {**row, "metadata_evidence": []})["metadata_evidence"].append(
                fact.model_dump(mode="json"))
    return list(matched.values())[:limit]
