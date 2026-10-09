import asyncio
import math
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from fastembed import TextEmbedding
from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError

from app.providers.base import BaseEmbeddingProvider, Embedding


class FastEmbedProvider(BaseEmbeddingProvider):
    MODEL_NAME = "BAAI/bge-small-en-v1.5"
    SPACE_ID = "fastembed:bge-small-en-v1.5:384:l2:v1"
    MODEL_REPO = "Qdrant/bge-small-en-v1.5-onnx-Q"
    MODEL_REVISION = "aa8f8b060edb00e03bfdd08813a2949946c8ba55"

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
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdf-embeddings")
        self._pending = 0

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

        return await self._submit(tuple(texts), False)

    async def embed_query(self, text: str) -> Embedding:
        vectors = await self._submit((text,), True)
        return vectors[0]

    async def _submit(self, texts, is_query):
        if self._pending >= 8:
            raise RuntimeError("Embedding capacity is busy; retry shortly.")
        self._pending += 1
        try:
            future = asyncio.get_running_loop().run_in_executor(self._executor, self._embed, texts, is_query)
        except BaseException:
            self._pending -= 1
            raise

        def finished(result):
            self._pending -= 1
            # Retrieve background errors even if the caller has been cancelled.
            if not result.cancelled():
                result.exception()
        future.add_done_callback(finished)
        return await asyncio.shield(future)

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)

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
                download_options = dict(repo_id=self.MODEL_REPO, revision=self.MODEL_REVISION,
                                        cache_dir=str(self._cache_dir),
                                        allow_patterns=["config.json", "special_tokens_map.json", "tokenizer.json",
                                                        "tokenizer_config.json", "model_optimized.onnx"])
                try:
                    model_path = snapshot_download(**download_options, local_files_only=True)
                except LocalEntryNotFoundError:
                    model_path = snapshot_download(**download_options)
                self._model = TextEmbedding(
                    model_name=self.MODEL_NAME,
                    cache_dir=str(self._cache_dir),
                    threads=self._threads,
                    specific_model_path=model_path,
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
