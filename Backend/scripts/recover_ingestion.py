"""Retry failed retained sources explicitly; pending work recovers automatically."""
import argparse
import asyncio
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.providers.embeddings import get_embedding_provider
from app.services.ingestion import ingest_pdf
from app.storage.db import Database
from app.storage.models import Document
from run import create_event_loop


async def retry(document_id):
    database = Database(get_settings())
    try:
        async with database.transaction() as connection:
            row = (await connection.execute(select(Document.filename, Document.original_pdf).where(
                Document.id == document_id, Document.status.in_(["failed", "pending"]),
            ))).one_or_none()
        if row is None or row.original_pdf is None:
            raise RuntimeError("No retained retryable source; re-upload the original PDF.")
        result = await ingest_pdf(database=database, embeddings=get_embedding_provider(),
                                  filename=row.filename, data=row.original_pdf)
        print(f"Document {result.document_id}: {result.status}")
    finally:
        await database.close()
        if get_embedding_provider.cache_info().currsize:
            get_embedding_provider().close()
            get_embedding_provider.cache_clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_id", type=UUID)
    args = parser.parse_args()
    try:
        with asyncio.Runner(loop_factory=create_event_loop) as runner:
            runner.run(retry(args.document_id))
    except Exception as exc:
        parser.exit(1, f"Recovery failed ({type(exc).__name__}).\n")


if __name__ == "__main__":
    main()
