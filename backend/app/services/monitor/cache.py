"""实时数据缓存管理器：进程内 TTL 缓存，/monitor/realtime 5s、temperatures 15s。"""

from __future__ import annotations

import time


class TTLCache:
    """进程内 key→value TTL 缓存：过期条目在读取时惰性剔除。

    模块尾部的 realtime_cache 为全局单例，供 /monitor/realtime（5s）与
    temperatures（15s）等高频接口复用。

    Attributes:
        _store (dict[str, tuple[float, object]]): key → (过期 monotonic 时刻, 数据)。
    """

    def __init__(self) -> None:
        """创建空缓存。"""
        self._store: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> object | None:
        """取缓存值，已过期即剔除并视为未命中。

        Args:
            key (str): 缓存键。

        Returns:
            object | None: 未过期数据；未命中或已过期时 None。
        """
        item = self._store.get(key)
        if not item:
            return None
        expires, data = item
        if time.monotonic() > expires:
            self._store.pop(key, None)
            return None
        return data

    def set(self, key: str, data: object, ttl: float) -> None:
        """写入缓存并设置存活时长（同 key 覆盖旧值）。

        Args:
            key (str): 缓存键。
            data (object): 任意缓存数据。
            ttl (float): 存活时长（秒，自当前 monotonic 时刻起算）。
        """
        self._store[key] = (time.monotonic() + ttl, data)


realtime_cache = TTLCache()
