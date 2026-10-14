"""Bounded process-local snapshots; database revisions remain authoritative."""
import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Generic, TypeVar
from uuid import UUID

T = TypeVar("T")


class ConfigurationCache(Generic[T]):
    def __init__(self, ttl_seconds: float, max_entries: int,
                 clock: Callable[[], float] = monotonic) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self._entries: OrderedDict[UUID, tuple[float, T]] = OrderedDict()
        self._loading: dict[UUID, asyncio.Task[T]] = {}
        self._tasks: set[asyncio.Task[T]] = set()
        self.hits = self.misses = self.invalidations = 0

    def invalidate(self, identifier: UUID | None = None) -> None:
        self.invalidations += 1
        if identifier is None:
            self._entries.clear()
            # Old callers may finish, but cannot publish into the new generation.
            self._loading.clear()
        else:
            self._entries.pop(identifier, None)
            self._loading.pop(identifier, None)

    async def get(self, identifier: UUID, loader: Callable[[], Awaitable[T]]) -> tuple[T, bool]:
        now = self.clock()
        for key, (deadline, _) in list(self._entries.items()):
            if deadline <= now:
                self._entries.pop(key)
        entry = self._entries.get(identifier)
        if entry is not None:
            self.hits += 1
            self._entries.move_to_end(identifier)
            return entry[1], True
        self.misses += 1
        if self.ttl_seconds == 0:
            return await loader(), False
        task = self._loading.get(identifier)
        if task is None:
            async def load() -> T:
                try:
                    result = await loader()
                    if self._loading.get(identifier) is asyncio.current_task():
                        self._entries[identifier] = (self.clock() + self.ttl_seconds, result)
                        self._entries.move_to_end(identifier)
                        while len(self._entries) > self.max_entries:
                            self._entries.popitem(last=False)
                    return result
                finally:
                    if self._loading.get(identifier) is asyncio.current_task():
                        self._loading.pop(identifier, None)
            task = asyncio.create_task(load(), name="assistant-configuration-load")
            # Retrieve failures even if every waiting HTTP request is cancelled.
            task.add_done_callback(lambda finished: None if finished.cancelled() else finished.exception())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            self._loading[identifier] = task
        return await asyncio.shield(task), False

    async def close(self) -> None:
        self.invalidate()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def snapshot(self) -> dict:
        return {"scope": "this_process", "ttl_seconds": self.ttl_seconds,
                "max_entries": self.max_entries, "entries": sum(
                    deadline > self.clock() for deadline, _ in self._entries.values()),
                "hits": self.hits, "misses": self.misses, "invalidations": self.invalidations}
