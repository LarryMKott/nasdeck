"""采集器基类：统一 collect() → dict 属性接口；子类只管取数，降级自己兜。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """硬件清单采集器基类：统一 ``collect() -> dict`` 属性接口。

    子类只管取数，降级自己兜；kind 标识采集域（cpu/gpu/memory/board/nic/raid_card），
    数据来源由各子类自定（psutil、/proc 与 /sys 内核文件直读、storcli+lspci 等）。
    """

    kind: str = "unknown"

    @abstractmethod
    async def collect(self) -> dict:
        """采集本域硬件信息，返回 {name, available, <props>}。

        实现内部自行降级，不抛异常。

        Returns:
            dict: name 为该域主标识（无数据为空串），available 表示是否采到，
                其余键为各域专有属性。
        """

    async def safe_collect(self) -> dict:
        """执行 collect() 并兜底：任何异常都转为统一错误标记，采集永不中断调度。

        Returns:
            dict: 正常时为 collect() 的结果；异常时为
                {"name": "", "available": False, "error": <异常描述>}。
        """
        try:
            return await self.collect()
        except Exception as exc:  # 采集永不中断调度
            logger.warning("采集器 %s 异常: %s", self.kind, exc)
            return {"name": "", "available": False, "error": str(exc)}
