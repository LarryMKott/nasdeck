"""5 分钟级日志哨兵拍：journalctl 扫描 → 命中事件落库广播（smartctl 重 fork
的同类低频处理；journalctl 缺失/无权限静默跳过）。"""

from __future__ import annotations

import logging

from app.db.session import session_factory
from app.services.system import log_watch

logger = logging.getLogger(__name__)


async def log_5m_tick() -> None:
    """日志哨兵拍（调度器 5 分钟间隔驱动；异常吞掉不拖垮调度轮）。"""
    try:
        events = await log_watch.watch_tick()
        if events:
            async with session_factory() as db:
                await log_watch.persist_and_notify(db, events)
                await db.commit()
            logger.warning("日志哨兵命中 %d 行", len(events))
    except Exception as exc:  # noqa: BLE001
        logger.warning("log_5m 异常: %s", exc)
