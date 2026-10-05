"""10 分钟级巡检调度拍：读计划配置，命中窗口即起独立巡检 task（smartctl 重 fork，
不进 1s/5s/60s 快车道；配置读库零 fork，拍本身开销可忽略）。"""

from __future__ import annotations

import logging

from app.db.session import session_factory
from app.services.storage import selftest_schedule

logger = logging.getLogger(__name__)


async def selftest_tick() -> None:
    try:
        async with session_factory() as db:
            fired = await selftest_schedule.schedule_tick(db)
            await db.commit()
        if fired:
            logger.info("周期巡检已触发（独立 task 执行中）")
    except Exception as exc:  # noqa: BLE001
        logger.warning("selftest_tick 异常: %s", exc)
