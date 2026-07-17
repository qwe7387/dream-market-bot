import asyncio
import unittest

from services.cache import EconomyCache


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_get_and_copy(self) -> None:
        cache = EconomyCache(ttl_seconds=10)
        value = {"item": "White Scroll", "avg_price": 1}
        await cache.set("White Scroll", 7, value)
        result = await cache.get(" white   scroll ", 7)
        self.assertEqual(result, value)
        result["avg_price"] = 999
        self.assertEqual((await cache.get("White Scroll", 7))["avg_price"], 1)

    async def test_expired_entry(self) -> None:
        cache = EconomyCache(ttl_seconds=0.01)
        await cache.set("Item", 7, {"avg_price": 1})
        await asyncio.sleep(0.02)
        self.assertIsNone(await cache.get("Item", 7))


if __name__ == "__main__":
    unittest.main()
