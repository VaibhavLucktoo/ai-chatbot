"""Document catalog and assistant-scope queries with short transactions."""

from sqlalchemy import func, select

from app.services.configuration_errors import AssistantNotFound
from app.storage.models import (
    Assistant,
    AssistantDocument,
    Document,
    DocumentChunk,
    ProviderConnection,
)


def metadata_query():
    chunk_count = (
        select(func.count())
        .select_from(DocumentChunk)
        .where(
            DocumentChunk.document_id == Document.id,
        )
        .correlate(Document)
        .scalar_subquery()
    )
    return select(
        Document.id,
        Document.filename,
        Document.page_count,
        Document.status,
        Document.created_at,
        Document.active,
        chunk_count.label("chunk_count"),
        Document.original_pdf.is_not(None).label("source_available"),
    )


async def list_documents(database, *, limit, offset, status=None, active=None):
    filters = []
    if status is not None:
        filters.append(Document.status == status)
    if active is not None:
        filters.append(Document.active == active)
    async with database.transaction() as connection:
        total = await connection.scalar(
            select(func.count()).select_from(Document).where(*filters)
        )
        rows = (
            (
                await connection.execute(
                    metadata_query()
                    .where(*filters)
                    .order_by(
                        Document.created_at.desc(),
                        Document.id,
                    )
                    .offset(offset)
                    .limit(limit)
                )
            )
            .mappings()
            .all()
        )
    return total, rows


async def get_document(database, document_id):
    async with database.transaction() as connection:
        row = (
            (
                await connection.execute(
                    metadata_query().where(Document.id == document_id)
                )
            )
            .mappings()
            .one_or_none()
        )
    return row


async def download_source(database, document_id):
    async with database.transaction() as connection:
        row = (
            await connection.execute(
                select(Document.filename, Document.original_pdf).where(
                    Document.id == document_id,
                )
            )
        ).one_or_none()
    return row


async def get_source_chunk(database, document_id, chunk_id):
    async with database.transaction() as connection:
        row = (
            (
                await connection.execute(
                    select(
                        DocumentChunk.id,
                        DocumentChunk.document_id,
                        Document.filename,
                        DocumentChunk.page_number,
                        DocumentChunk.chunk_index,
                        DocumentChunk.content,
                    )
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(
                        Document.id == document_id,
                        DocumentChunk.id == chunk_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
    return row


async def assistant_documents(database, assistant_id, *, limit, offset):
    async with database.transaction() as connection:
        available = await connection.scalar(
            select(Assistant.id)
            .join(ProviderConnection)
            .where(
                Assistant.id == assistant_id,
                Assistant.active.is_(True),
                ProviderConnection.active.is_(True),
            )
        )
        if available is None:
            raise AssistantNotFound("Assistant is missing or disabled.")
        filters = [
            Document.status == "ready",
            Document.active.is_(True),
            Document.id.in_(
                select(AssistantDocument.document_id).where(
                    AssistantDocument.assistant_id == assistant_id
                )
            ),
        ]
        total = await connection.scalar(
            select(func.count()).select_from(Document).where(*filters)
        )
        rows = (
            (
                await connection.execute(
                    metadata_query()
                    .where(*filters)
                    .order_by(Document.created_at.desc(), Document.id)
                    .offset(offset)
                    .limit(limit)
                )
            )
            .mappings()
            .all()
        )
    return total, rows
