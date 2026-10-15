"""Durable upload claims and status queries."""

from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.storage.models import Document


async def enqueue_document(database, *, filename, digest, data):
    async with database.transaction() as connection:
        await connection.execute(
            insert(Document)
            .values(
                id=uuid4(),
                filename=filename,
                content_sha256=digest,
                original_pdf=data,
                page_count=1,
                status="pending",
                lease_expires_at=func.now(),
            )
            .on_conflict_do_nothing(index_elements=[Document.content_sha256])
        )
        # Explicit resubmission retries failures. Preserve an active owner.
        await connection.execute(
            update(Document)
            .where(
                Document.content_sha256 == digest,
                Document.status == "failed",
            )
            .values(
                status="pending",
                original_pdf=data,
                lease_expires_at=func.now(),
                attempt_id=None,
                ingestion_attempts=0,
            )
        )
        await connection.execute(
            update(Document)
            .where(
                Document.content_sha256 == digest,
                Document.status == "ready",
                Document.original_pdf.is_(None),
            )
            .values(original_pdf=data)
        )
        row = (
            await connection.execute(
                select(Document.id, Document.filename, Document.status).where(
                    Document.content_sha256 == digest,
                )
            )
        ).one()
    return row


async def job_status(database, document_id):
    async with database.transaction() as connection:
        row = (
            await connection.execute(
                select(Document.id, Document.filename, Document.status).where(
                    Document.id == document_id,
                )
            )
        ).one_or_none()
    return row
