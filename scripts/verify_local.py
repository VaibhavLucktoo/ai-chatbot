"""Verify startup/readiness and optionally a restored database without LLM calls."""
import argparse
import asyncio
from hashlib import sha256
import re

import httpx
from sqlalchemy import func, select

from app.core.config import get_settings
from app.storage.db import Database
from app.storage.models import Document, DocumentChunk
from run import create_event_loop


async def fingerprint(database):
    digest, count = sha256(), 0
    async with database.session() as session:
        async with session.begin():
            result = await session.stream(select(Document.id, Document.content_sha256, Document.original_pdf,
                                                  Document.status, Document.active).order_by(Document.id))
            async for row in result:
                if row.original_pdf is not None and sha256(row.original_pdf).hexdigest() != row.content_sha256:
                    raise RuntimeError("Retained source integrity mismatch.")
                digest.update(str((row.id, row.content_sha256, row.status, row.active)).encode())
                digest.update(sha256(row.original_pdf).digest() if row.original_pdf is not None else b"legacy")
                count += 1
            chunks = await session.scalar(select(func.count()).select_from(DocumentChunk))
    return count, chunks, digest.hexdigest()


async def verify(restore_database=None):
    from app.main import create_app
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            for path in ("/v1/health", "/v1/ready", "/admin"):
                response = await client.get(path)
                if response.status_code != 200:
                    raise RuntimeError("Startup smoke check failed.")
            for path in ("/v1/admin/status", "/v1/admin/documents"):
                response = await client.get(path, headers={"X-Admin-Token": app.state.admin_token})
                if response.status_code != 200:
                    raise RuntimeError("Admin diagnostics smoke check failed.")
        print("Startup, embedding warmup, health, readiness, and admin checks passed.")
        if restore_database:
            restored = Database(get_settings().model_copy(update={"postgres_db": restore_database}))
            try:
                if not await restored.is_ready(check_schema=True):
                    raise RuntimeError("Restored schema is not ready.")
                if await fingerprint(app.state.database) != await fingerprint(restored):
                    raise RuntimeError("Restored source identity or document/chunk counts differ.")
                print("Restore schema, document identities, retained source hashes and chunk counts match.")
            finally:
                await restored.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore-database")
    args = parser.parse_args()
    if args.restore_database and not re.fullmatch(r"restore_[a-z0-9_]{1,48}", args.restore_database):
        parser.error("Use a restore_* database name.")
    try:
        with asyncio.Runner(loop_factory=create_event_loop) as runner:
            runner.run(verify(args.restore_database))
    except Exception as exc:
        parser.exit(1, f"Verification failed ({type(exc).__name__}).\n")


if __name__ == "__main__":
    main()
