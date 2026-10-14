from abc import ABC, abstractmethod
from collections.abc import Sequence

Embedding = list[float]


class BaseEmbeddingProvider(ABC):
    @property
    @abstractmethod
    def space_id(self) -> str:
        """Identify the model and preprocessing configuration."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        ...

    @abstractmethod
    async def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[Embedding]:
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> Embedding:
        ...