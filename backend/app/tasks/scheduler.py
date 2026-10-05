"""全局调度器任务注册：快/中/慢三档实时采集 + 15 分钟存储趋势 + 10 分钟巡检拍 + 历史降采样。

间隔档位与采集哲学（低占用架构约定）对应：
- 1s/5s/60s：/proc、/sys 内核文件直读为主，外部命令只允许进 5s/60s 档；
- 15m（smart_15m/volume_15m）：smartctl 等重 fork 的存储趋势采样；
- 10m（selftest_10m）：巡检计划拍（读库判定窗口，命中才 fork smartctl）；
- 5m downsample：历史聚合与保留窗清理。
全部 job max_instances=1 + coalesce，机慢时合并执行不堆积。
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.tasks.collectors.fast_1s import fast_tick
from app.tasks.collectors.log_5m import log_5m_tick
from app.tasks.collectors.medium_5s import medium_tick
from app.tasks.collectors.report_10m import report_10m_tick
from app.tasks.collectors.selftest_10m import selftest_tick
from app.tasks.collectors.slow_60s import slow_tick
from app.tasks.collectors.smart_15m import smart_15m_tick
from app.tasks.collectors.volume_15m import volume_15m_tick
from app.tasks.downsampler import downsample_tick

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


def start_jobs() -> None:
    """注册全部周期任务：1s/5s/60s 实时采集 + 15m×2 趋势 + 10m 巡检 + 5m 降采样。

    除 downsample 外全部 max_instances=1 + coalesce，机慢时合并执行不堆积。
    """
    scheduler.add_job(fast_tick, "interval", seconds=1, id="fast_1s", max_instances=1, coalesce=True)
    scheduler.add_job(medium_tick, "interval", seconds=5, id="medium_5s", max_instances=1, coalesce=True)
    scheduler.add_job(slow_tick, "interval", seconds=60, id="slow_60s", max_instances=1, coalesce=True)
    scheduler.add_job(smart_15m_tick, "interval", minutes=15, id="smart_15m", max_instances=1, coalesce=True)
    scheduler.add_job(volume_15m_tick, "interval", minutes=15, id="volume_15m", max_instances=1, coalesce=True)
    scheduler.add_job(selftest_tick, "interval", minutes=10, id="selftest_10m", max_instances=1, coalesce=True)
    scheduler.add_job(downsample_tick, "interval", minutes=5, id="downsample", max_instances=1)
    scheduler.add_job(log_5m_tick, "interval", minutes=5, id="log_5m", max_instances=1, coalesce=True)
    scheduler.add_job(report_10m_tick, "interval", minutes=10, id="report_10m", max_instances=1, coalesce=True)
    logger.info("调度器任务注册完成")


def start() -> None:
    """启动全局调度器；尚未注册任务时先补一次 start_jobs()。"""
    if not scheduler.get_jobs():
        start_jobs()
    scheduler.start()


def shutdown(wait: bool = False) -> None:
    """停止全局调度器（未在运行时静默跳过）。

    Args:
        wait: True 时等待正在执行的任务结束再返回。
    """
    if scheduler.running:
        scheduler.shutdown(wait=wait)
