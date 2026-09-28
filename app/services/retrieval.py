"""Query embedding and document retrieval orchestration."""

import math
from dataclasses import dataclass

from app.providers.base import BaseEmbeddingProvider
from app.storage.db import Database
from app.storage.documents import StoredChunkResult, search_similar_chunks
from app.storage.models import EMBEDDING_DIMENSIONS, EMBEDDING_SPACE


class RetrievalProviderError(RuntimeError):
    """Embedding provider failed or violated its output contract."""


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Normalized query and its ranked passages."""

    query: str
    top_k: int
    chunks: list[StoredChunkResult]


async def retrieve_chunks(
    database: Database,
    embeddings: BaseEmbeddingProvider,
    query: str,
    top_k: int = 5,
) -> RetrievalResult:
    """Generate one query embedding and execute one vector search."""

    if not isinstance(query, str):
        raise ValueError("Query must be text.")

    normalized_query = query.strip()

    if not normalized_query:
        raise ValueError("Query cannot be blank.")

    if type(top_k) is not int or not 1 <= top_k <= 20:
        raise ValueError("top_k must be an integer between 1 and 20.")

    if (
        embeddings.dimensions != EMBEDDING_DIMENSIONS
        or embeddings.space_id != EMBEDDING_SPACE
    ):
        raise RetrievalProviderError(
            "Embedding provider does not match the stored vector space."
        )

    try:
        raw_vector = await embeddings.embed_query(normalized_query)
        vector = [float(value) for value in raw_vector]
    except Exception as exc:
        raise RetrievalProviderError(
            "Query embedding generation failed."
        ) from exc

    if len(vector) != EMBEDDING_DIMENSIONS:
        raise RetrievalProviderError(
            "Embedding provider returned incorrect dimensions."
        )

    if not all(math.isfinite(value) for value in vector):
        raise RetrievalProviderError(
            "Embedding provider returned non-finite values."
        )

    if not any(value != 0.0 for value in vector):
        raise RetrievalProviderError(
            "Embedding provider returned a zero vector."
        )

    if not math.isclose(math.hypot(*vector), 1.0, rel_tol=1e-5):
        raise RetrievalProviderError(
            "Embedding provider returned a vector without L2 normalization."
        )

    chunks = await search_similar_chunks(
        database=database,
        query_vector=vector,
        top_k=top_k,
    )

    return RetrievalResult(
        query=normalized_query,
        top_k=top_k,
        chunks=chunks,
    )
