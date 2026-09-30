"""采集器基类：统一 collect() → dict 属性接口；子类只管取数，降级自己兜。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    kind: str = "unknown"

    @abstractmethod
    async def collect(self) -> dict:
        """返回 {name, available, <props>}；实现内部自行降级，不抛异常。"""

    async def safe_collect(self) -> dict:
        try:
            return await self.collect()
        except Exception as exc:  # 采集永不中断调度
            logger.warning("采集器 %s 异常: %s", self.kind, exc)
            return {"name": "", "available": False, "error": str(exc)}
