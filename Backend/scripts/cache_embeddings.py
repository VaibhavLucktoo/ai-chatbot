"""Download and verify pinned embedding assets while building the container."""

import asyncio

from app.core.config import CACHE_ROOT
from app.providers.fastembed_provider import FastEmbedProvider


async def main():
    provider = FastEmbedProvider(cache_dir=CACHE_ROOT / "fastembed", threads=2)
    try:
        await provider.embed_query("Container embedding readiness")
    finally:
        provider.close()


if __name__ == "__main__":
    asyncio.run(main())
