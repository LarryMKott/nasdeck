"""1 秒级采集：系统资源快照 → 实时缓存 + metrics 原始点落库。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.session import session_factory
from app.models.metrics import MetricPoint
from app.services.monitor import system_resources
from app.services.monitor.cache import realtime_cache

logger = logging.getLogger(__name__)


async def fast_tick() -> None:
    try:
        snap = await system_resources.snapshot()
        # GPU 分量由 medium_5s 以 5s 采样维护（本 tick 只并入缓存与落库，不重复采集）
        snap["gpu"] = realtime_cache.get("gpu")
        realtime_cache.set("realtime", snap, ttl=5)
        async with session_factory() as db:
            net_kbps = round(sum(i["rx_kbps"] + i["tx_kbps"] for i in snap["net"].values()), 1)
            # 秒级时间戳是唯一键：调度器首跑与下一轮偶发落在同一秒，冲突即忽略防丢整轮
            stmt = (
                sqlite_insert(MetricPoint)
                .values(
                    ts=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
                    granularity="raw",
                    cpu=snap["cpu_percent"],
                    mem_mb=snap["mem_used_mb"],
                    net_kbps=net_kbps,
                    temp_max=None,  # 温度由 medium_5s 回填到缓存与下轮落库
                    gpu=(snap["gpu"] or {}).get("percent"),
                    disk_read_kbps=snap["disk_io"].get("read_kbps"),
                    disk_write_kbps=snap["disk_io"].get("write_kbps"),
                )
                .on_conflict_do_nothing(index_elements=["ts", "granularity"])
            )
            await db.execute(stmt)
            await db.commit()
    except Exception as exc:  # noqa: BLE001 采集任务不中断调度
        logger.warning("fast_tick 异常: %s", exc)
