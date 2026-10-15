"""Build missing metadata for ready documents without changing original chunks."""

import argparse
import asyncio
import json

from app.core.config import get_settings
from app.providers.embeddings import get_embedding_provider
from app.services.document_metadata import ensure_document_metadata
from app.storage.db import Database
from app.storage.document_metadata import missing_metadata_ids
from run import create_event_loop


async def backfill(*, apply=False):
    database = Database(get_settings())
    scanned = updated = 0
    after = None
    try:
        embeddings = get_embedding_provider() if apply else None
        while identifiers := await missing_metadata_ids(database, after=after):
            for identifier in identifiers:
                scanned += 1
                if apply:
                    updated += await ensure_document_metadata(database, embeddings, identifier)
            after = identifiers[-1]
        print(json.dumps({"mode": "apply" if apply else "dry-run", "documents_missing_metadata": scanned,
                          "documents_updated": updated}))
    finally:
        await database.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist missing/outdated metadata (default: read-only count).")
    args = parser.parse_args()
    with asyncio.Runner(loop_factory=create_event_loop) as runner:
        runner.run(backfill(apply=args.apply))


if __name__ == "__main__":
    main()
