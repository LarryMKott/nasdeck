"""实时数据缓存管理器：进程内 TTL 缓存，/monitor/realtime 5s、temperatures 15s。"""

from __future__ import annotations

import time


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> object | None:
        item = self._store.get(key)
        if not item:
            return None
        expires, data = item
        if time.monotonic() > expires:
            self._store.pop(key, None)
            return None
        return data

    def set(self, key: str, data: object, ttl: float) -> None:
        self._store[key] = (time.monotonic() + ttl, data)

    def pop(self, key: str) -> None:
        self._store.pop(key, None)


realtime_cache = TTLCache()
