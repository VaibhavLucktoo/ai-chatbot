import argparse
import asyncio
from pathlib import Path
import sys

# Support both python -m scripts.ingest and python scripts/ingest.py.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.documents import MAX_PDF_BYTES, PDFExtractionError


def read_pdf(path: Path) -> bytes:
    with path.open("rb") as source:
        data = source.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise PDFExtractionError("The PDF exceeds the 10 MB limit.")
    return data


async def ingest_file(path: Path) -> None:
    # Load database and model dependencies only for an actual ingestion.
    from app.core.config import get_settings
    from app.providers.embeddings import get_embedding_provider
    from app.services.ingestion import ingest_pdf
    from app.storage.db import Database

    database = Database(get_settings())

    try:
        if not await database.is_ready():
            raise RuntimeError("Database is not ready.")

        result = await ingest_pdf(
            database=database,
            embeddings=get_embedding_provider(),
            filename=path.name,
            data=await asyncio.to_thread(read_pdf, path),
        )

        if result.status != "ready":
            raise RuntimeError("This PDF is already being processed. Retry later.")

        print(f"Document ID: {result.document_id}")
        print(f"Status: {result.status}")
        print(f"Pages: {result.page_count}")
        print(f"Chunks: {result.chunk_count}")
        print(f"Already existed: {result.already_existed}")
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index a PDF: uv run python -m scripts.ingest document.pdf",
    )
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()

    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")

    from sqlalchemy.exc import SQLAlchemyError
    from app.services.chunking import ChunkingError
    from run import create_event_loop

    try:
        with asyncio.Runner(loop_factory=create_event_loop) as runner:
            runner.run(ingest_file(args.pdf))
    except SQLAlchemyError:
        parser.exit(1, "Ingestion failed: document storage is unavailable. Retry later.\n")
    except (PDFExtractionError, ChunkingError, RuntimeError, OSError) as exc:
        parser.exit(1, f"Ingestion failed: {exc}\n")


if __name__ == "__main__":
    main()
