from functools import lru_cache

from app.core.config import get_settings
from app.providers.base import BaseEmbeddingProvider


@lru_cache(maxsize=1)
def get_embedding_provider() -> BaseEmbeddingProvider:
    settings = get_settings()

    if settings.embedding_provider != "fastembed":
        raise ValueError(
            f"Unsupported embedding provider: {settings.embedding_provider}"
        )

    # Import only the selected implementation.
    from app.providers.fastembed_provider import FastEmbedProvider

    if settings.embedding_model != FastEmbedProvider.MODEL_NAME:
        raise ValueError("This adapter supports only BGE-small-en-v1.5.")

    provider = FastEmbedProvider(
        cache_dir=settings.embedding_cache_dir,
        threads=settings.embedding_threads,
    )

    if settings.embedding_dimensions != provider.dimensions:
        raise ValueError("Configured embedding dimensions do not match.")

    return provider