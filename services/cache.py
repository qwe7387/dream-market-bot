from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    value: dict[str, Any]
    expires_at: float


class EconomyCache:
    """Small in-memory TTL cache for Economy API responses."""

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._entries: dict[tuple[str, int], CacheEntry] = {}
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(item_name: str, period: int) -> tuple[str, int]:
        normalized = " ".join(item_name.strip().split()).casefold()
        return normalized, int(period)

    async def get(self, item_name: str, period: int) -> dict[str, Any] | None:
        if self.ttl_seconds <= 0:
            self.misses += 1
            return None

        key = self._key(item_name, period)
        now = time.monotonic()

        async with self._lock:
            entry = self._entries.get(key)

            if entry is None:
                self.misses += 1
                return None

            if entry.expires_at <= now:
                self._entries.pop(key, None)
                self.misses += 1
                return None

            self.hits += 1
            return deepcopy(entry.value)

    async def set(
        self,
        item_name: str,
        period: int,
        value: dict[str, Any],
    ) -> None:
        if self.ttl_seconds <= 0:
            return

        key = self._key(item_name, period)
        entry = CacheEntry(
            value=deepcopy(value),
            expires_at=time.monotonic() + self.ttl_seconds,
        )

        async with self._lock:
            self._entries[key] = entry

    async def clear(self) -> int:
        async with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count

    async def size(self) -> int:
        now = time.monotonic()

        async with self._lock:
            expired = [
                key
                for key, entry in self._entries.items()
                if entry.expires_at <= now
            ]

            for key in expired:
                self._entries.pop(key, None)

            return len(self._entries)
