"""Read-only SQL for local operator document diagnostics."""

from sqlalchemy import func, select

from app.storage.models import Document, DocumentChunk


async def read_admin_documents(db, *, limit, offset):
    async with db.begin():
        total = await db.scalar(select(func.count()).select_from(Document))
        statement = (
            select(
                Document.id,
                Document.filename,
                Document.page_count,
                Document.status,
                Document.created_at,
                Document.active,
                Document.processing_metadata,
                func.count(DocumentChunk.id).label("chunk_count"),
                (Document.lease_expires_at > func.now()).label("lease_active"),
            )
            .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
            .group_by(
                Document.id,
            )
            .order_by(Document.created_at.desc(), Document.id)
            .offset(offset)
            .limit(limit)
        )
        rows = (await db.execute(statement)).mappings().all()
    return total, rows
