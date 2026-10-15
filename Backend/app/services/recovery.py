"""Recover expired ingestion attempts from retained database sources."""
import asyncio
import logging

from sqlalchemy import func, or_, select, update

from app.providers.embeddings import get_embedding_provider
from app.services.ingestion import ingest_pdf
from app.providers.documents import PDFExtractionError
from app.services.document_hash import pdf_sha256
from app.storage.models import Document
from app.storage.documents import DocumentClaimLostError

logger = logging.getLogger(__name__)


async def recover_once(database):
    # Read one source at a time; never load the entire retained corpus.
    async with database.transaction() as connection:
        row = (await connection.execute(select(Document.id, Document.filename, Document.original_pdf,
                                                Document.attempt_id, Document.ingestion_attempts,
                                                Document.content_sha256).where(
            Document.status == "pending", Document.original_pdf.is_not(None),
            or_(Document.lease_expires_at.is_(None), Document.lease_expires_at <= func.now()),
        ).order_by(Document.created_at, Document.id).limit(1))).one_or_none()
    if row is None:
        return False
    # ingest_pdf uses a fenced database claim; concurrent workers cannot publish
    # the same attempt or replace the results of a newer owner.
    try:
        if row.ingestion_attempts >= 3 or pdf_sha256(row.original_pdf) != row.content_sha256:
            raise PDFExtractionError("Recovery attempt limit or source integrity check failed.")
        await ingest_pdf(database=database, embeddings=get_embedding_provider(),
                         filename=row.filename, data=row.original_pdf, expected_document_id=row.id)
    except DocumentClaimLostError:
        # Deletion won the race. It is a completed cancellation, not retryable work.
        return True
    except PDFExtractionError as exc:
        logger.warning("Queued PDF rejected document_id=%s reason=%s", row.id, str(exc))
        # Invalid queued bytes fail before ingest_pdf can claim an attempt.
        # Do not change an owner that started after our selection snapshot.
        async with database.transaction() as connection:
            await connection.execute(update(Document).where(
                Document.id == row.id, Document.status == "pending",
                Document.attempt_id == row.attempt_id,
                or_(Document.lease_expires_at.is_(None), Document.lease_expires_at <= func.now()),
            ).values(status="failed", attempt_id=None, lease_expires_at=None))
    return True


async def recovery_loop(database):
    while True:
        try:
            if await recover_once(database):
                continue
        except Exception as exc:
            logger.warning("Ingestion recovery failed (%s)", type(exc).__name__)
        await asyncio.sleep(database.settings.ingestion_recovery_interval_seconds)
