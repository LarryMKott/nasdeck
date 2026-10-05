"""全局调度器：1s/5s/60s 三级采集 + 历史降采样（契约对应 tasks/collectors）。"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.tasks.collectors.fast_1s import fast_tick
from app.tasks.collectors.medium_5s import medium_tick
from app.tasks.collectors.selftest_10m import selftest_tick
from app.tasks.collectors.slow_60s import slow_tick
from app.tasks.collectors.smart_15m import smart_15m_tick
from app.tasks.collectors.volume_15m import volume_15m_tick
from app.tasks.downsampler import downsample_tick

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


def start_jobs() -> None:
    scheduler.add_job(fast_tick, "interval", seconds=1, id="fast_1s", max_instances=1, coalesce=True)
    scheduler.add_job(medium_tick, "interval", seconds=5, id="medium_5s", max_instances=1, coalesce=True)
    scheduler.add_job(slow_tick, "interval", seconds=60, id="slow_60s", max_instances=1, coalesce=True)
    scheduler.add_job(smart_15m_tick, "interval", minutes=15, id="smart_15m", max_instances=1, coalesce=True)
    scheduler.add_job(volume_15m_tick, "interval", minutes=15, id="volume_15m", max_instances=1, coalesce=True)
    scheduler.add_job(selftest_tick, "interval", minutes=10, id="selftest_10m", max_instances=1, coalesce=True)
    scheduler.add_job(downsample_tick, "interval", minutes=5, id="downsample", max_instances=1)
    logger.info("调度器任务注册完成")


def start() -> None:
    if not scheduler.get_jobs():
        start_jobs()
    scheduler.start()


def shutdown(wait: bool = False) -> None:
    if scheduler.running:
        scheduler.shutdown(wait=wait)
