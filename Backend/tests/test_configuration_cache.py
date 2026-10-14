import asyncio
import unittest
from uuid import uuid4
from app.services.configuration_cache import ConfigurationCache


class ConfigurationCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_ttl_lru_and_no_negative_caching(self):
        now = [0.0]
        cache = ConfigurationCache(10, 2, lambda: now[0])
        calls = 0
        async def load():
            nonlocal calls
            calls += 1
            return calls
        a, b, c = uuid4(), uuid4(), uuid4()
        self.assertEqual(await cache.get(a, load), (1, False))
        await cache.get(b, load)
        self.assertEqual(await cache.get(a, load), (1, True))
        await cache.get(c, load)
        self.assertEqual(await cache.get(b, load), (4, False))
        now[0] = 10
        self.assertEqual(await cache.get(b, load), (5, False))
        async def fail():
            raise ValueError("configuration unavailable")
        identifier = uuid4()
        for _ in range(2):
            with self.assertRaises(ValueError):
                await cache.get(identifier, fail)
        self.assertEqual(await cache.get(identifier, load), (6, False))

    async def test_single_flight_cancellation_and_invalidation_fence(self):
        cache = ConfigurationCache(300, 2)
        identifier = uuid4()
        started, release = asyncio.Event(), asyncio.Event()
        calls = 0
        async def slow():
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return "old"
        first = asyncio.create_task(cache.get(identifier, slow))
        await started.wait()
        second = asyncio.create_task(cache.get(identifier, slow))
        await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        cache.invalidate(identifier)
        async def fresh():
            return "new"
        self.assertEqual(await cache.get(identifier, fresh), ("new", False))
        release.set()
        self.assertEqual(await second, ("old", False))
        self.assertEqual(calls, 1)
        self.assertEqual(await cache.get(identifier, fresh), ("new", True))
        cache.invalidate()
        self.assertEqual(await cache.get(identifier, fresh), ("new", False))

    async def test_disabled_cache(self):
        cache = ConfigurationCache(0, 2)
        async def load():
            return object()
        identifier = uuid4()
        first, _ = await cache.get(identifier, load)
        second, hit = await cache.get(identifier, load)
        self.assertIsNot(first, second)
        self.assertFalse(hit)
