"""Tiny async TTL cache.

USGS asks clients not to hammer the service, and the ETL only refreshes every
15–30 minutes anyway, so API responses are memoized for `cache_ttl_seconds`.
Concurrent callers for the same key share one computation.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CacheEntry:
    value: Any
    created_at: float

    def age_seconds(self, now: float | None = None) -> float:
        return (now if now is not None else time.monotonic()) - self.created_at


class TtlCache:
    def __init__(self, ttl_seconds: float) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def peek(self, key: str) -> CacheEntry | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.age_seconds() > self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        return entry

    async def get_or_set(self, key: str, factory: Callable[[], Awaitable[Any]]) -> Any:
        entry = self.peek(key)
        if entry is not None:
            return entry.value
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            entry = self.peek(key)
            if entry is not None:
                return entry.value
            value = await factory()
            self._entries[key] = CacheEntry(value=value, created_at=time.monotonic())
            return value

    def invalidate(self, key: str | None = None) -> None:
        if key is None:
            self._entries.clear()
        else:
            self._entries.pop(key, None)
