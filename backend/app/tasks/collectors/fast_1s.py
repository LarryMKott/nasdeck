"""1 秒级采集：系统资源快照 → 实时缓存；指标行投递 ingest 通道批量落库。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.db import ingest
from app.services.monitor import system_resources
from app.services.monitor import temperature as temperature_service
from app.services.monitor.cache import realtime_cache

logger = logging.getLogger(__name__)


async def fast_tick() -> None:
    """1 秒一轮：系统资源快照写入实时缓存，并向 ingest 通道投递一条 raw 指标行。

    GPU/温度分量由 medium_5s 采样维护缓存，本 tick 只并入与落库，不重复采集；
    温度内嵌进插入行（读缓存，滞后 ≤15s 对 1m/10m 聚合无感），替代旧
    "medium_tick 每 5s 回填最新行 UPDATE"方案。任何异常只记 warning，不中断调度。
    """
    try:
        snap = await system_resources.snapshot()
        # GPU / 温度分量由 medium_5s 采样维护缓存，本 tick 只并入与落库，不重复采集
        snap["gpu"] = realtime_cache.get("gpu")
        snap["top_procs"] = realtime_cache.get("top_procs")  # 进程风暴榜（花活二期 K）
        temps = realtime_cache.get("temperatures")
        realtime_cache.set("realtime", snap, ttl=5)  # WS 实时源，每秒更新
        # 温度内嵌进插入行（读缓存，滞后 ≤15s 对 1m/10m 聚合无感）：
        # 替代旧「medium_tick 每 5s 回填最新行 UPDATE」——此前 raw 表仅 1/5 行有温度
        ingest.submit(
            "metrics",
            {
                "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
                "granularity": "raw",
                "cpu": snap["cpu_percent"],
                "mem_mb": snap["mem_used_mb"],
                "net_kbps": round(sum(i["rx_kbps"] + i["tx_kbps"] for i in snap["net"].values()), 1),
                "temp_max": temperature_service.max_celsius(temps) if temps else None,
                "gpu": (snap["gpu"] or {}).get("percent"),
                "disk_read_kbps": snap["disk_io"].get("read_kbps"),
                "disk_write_kbps": snap["disk_io"].get("write_kbps"),
            },
        )
    except Exception as exc:  # noqa: BLE001 采集任务不中断调度
        logger.warning("fast_tick 异常: %s", exc)
