"""1 秒级采集：系统资源快照 → 实时缓存；指标行投递 ingest 通道批量落库。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.db import ingest
from app.services.monitor import system_resources
from app.services.monitor.cache import realtime_cache

logger = logging.getLogger(__name__)


async def fast_tick() -> None:
    try:
        snap = await system_resources.snapshot()
        # GPU 分量由 medium_5s 以 5s 采样维护（本 tick 只并入缓存与落库，不重复采集）
        snap["gpu"] = realtime_cache.get("gpu")
        realtime_cache.set("realtime", snap, ttl=5)  # WS 实时源，每秒更新
        # 指标行投递单写者通道攒批落盘（秒级时间戳唯一键，冲突由 ON CONFLICT 跳过）
        ingest.submit(
            "metrics",
            {
                "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
                "granularity": "raw",
                "cpu": snap["cpu_percent"],
                "mem_mb": snap["mem_used_mb"],
                "net_kbps": round(sum(i["rx_kbps"] + i["tx_kbps"] for i in snap["net"].values()), 1),
                "temp_max": None,  # 温度由 medium_5s 回填到缓存与下轮落库
                "gpu": (snap["gpu"] or {}).get("percent"),
                "disk_read_kbps": snap["disk_io"].get("read_kbps"),
                "disk_write_kbps": snap["disk_io"].get("write_kbps"),
            },
        )
    except Exception as exc:  # noqa: BLE001 采集任务不中断调度
        logger.warning("fast_tick 异常: %s", exc)
