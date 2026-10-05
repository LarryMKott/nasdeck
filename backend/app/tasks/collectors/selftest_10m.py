"""10 分钟级巡检调度拍：读计划配置，命中窗口即起独立巡检 task（smartctl 重 fork，
不进 1s/5s/60s 快车道；配置读库零 fork，拍本身开销可忽略）。"""

from __future__ import annotations

import logging

from app.db.session import session_factory
from app.services.storage import selftest_schedule

logger = logging.getLogger(__name__)


async def selftest_tick() -> None:
    """10 分钟巡检调度拍：读巡检计划配置，命中窗口即起独立巡检 task。

    配置读库零 fork，拍本身开销可忽略；smartctl 重 fork 由被触发的独立 task
    承担，不占本拍（不进 1s/5s/60s 快车道）。命中触发时记 info 日志；
    任何异常只记 warning，不中断调度。
    """
    try:
        async with session_factory() as db:
            fired = await selftest_schedule.schedule_tick(db)
            await db.commit()
        if fired:
            logger.info("周期巡检已触发（独立 task 执行中）")
    except Exception as exc:  # noqa: BLE001
        logger.warning("selftest_tick 异常: %s", exc)
