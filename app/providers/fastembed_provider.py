import asyncio
import math
from collections.abc import Sequence
from pathlib import Path
from threading import Lock

from fastembed import TextEmbedding

from app.providers.base import BaseEmbeddingProvider, Embedding


class FastEmbedProvider(BaseEmbeddingProvider):
    MODEL_NAME = "BAAI/bge-small-en-v1.5"
    SPACE_ID = "fastembed:bge-small-en-v1.5:384:l2:v1"

    def __init__(
        self,
        *,
        cache_dir: Path,
        threads: int = 2,
    ) -> None:
        self._cache_dir = cache_dir
        self._threads = threads
        self._model: TextEmbedding | None = None
        self._lock = Lock()

    @property
    def dimensions(self) -> int:
        return 384

    @property
    def space_id(self) -> str:
        return self.SPACE_ID

    async def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[Embedding]:
        if not texts:
            return []

        return await asyncio.to_thread(
            self._embed,
            tuple(texts),
            False,
        )

    async def embed_query(self, text: str) -> Embedding:
        vectors = await asyncio.to_thread(
            self._embed,
            (text,),
            True,
        )
        return vectors[0]

    def _embed(
        self,
        texts: tuple[str, ...],
        is_query: bool,
    ) -> list[Embedding]:
        if any(not text.strip() for text in texts):
            raise ValueError("Embedding input cannot be blank.")

        # Lazy loading and inference run outside FastAPI's event loop.
        # A threading lock also protects inference after task cancellation.
        with self._lock:
            if self._model is None:
                self._model = TextEmbedding(
                    model_name=self.MODEL_NAME,
                    cache_dir=str(self._cache_dir),
                    threads=self._threads,
                )

            if is_query:
                generated = self._model.query_embed(texts[0])
            else:
                generated = self._model.passage_embed(
                    texts,
                    batch_size=32,
                )

            vectors: list[Embedding] = []

            for vector in generated:
                values = [float(value) for value in vector]

                if len(values) != self.dimensions:
                    raise ValueError("Unexpected embedding dimensions.")

                if not all(math.isfinite(value) for value in values):
                    raise ValueError("Embedding contains non-finite values.")

                norm = math.sqrt(sum(value * value for value in values))
                if norm == 0:
                    raise ValueError("Embedding has zero magnitude.")

                vectors.append([value / norm for value in values])

        if len(vectors) != len(texts):
            raise ValueError("Embedding count does not match input count.")

        return vectors