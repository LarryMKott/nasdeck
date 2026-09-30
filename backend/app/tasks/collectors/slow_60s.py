"""60 秒级采集：硬件信息落库（SMART 依赖 smartctl，不可用即跳过）+ 磁盘/阵列健康刷新。"""

from __future__ import annotations

import logging

from app.db import ingest
from app.services.hardware.cpu import CpuCollector
from app.services.hardware.gpu import GpuCollector
from app.services.hardware.memory import MemoryCollector
from app.services.hardware.motherboard import MotherboardCollector
from app.services.hardware.nic import NicCollector
from app.services.hardware.raid_card import RaidCardCollector
from app.services.monitor.cache import realtime_cache
from app.services.storage import raid as raid_service
from app.services.storage import volumes as volume_service

logger = logging.getLogger(__name__)

_COLLECTORS = (
    CpuCollector(),
    GpuCollector(),
    MemoryCollector(),
    MotherboardCollector(),
    NicCollector(),
    RaidCardCollector(),
)


async def slow_tick() -> None:
    try:
        rows = [await c.safe_collect() for c in _COLLECTORS]
        logger.debug(
            "硬件采集: %s",
            " ".join(
                f"{c.kind}:{r.get('name') or '?'}({'ok' if r.get('available') else '缺'})"
                for c, r in zip(_COLLECTORS, rows, strict=False)
            ),
        )
        for c, r in zip(_COLLECTORS, rows, strict=False):
            ingest.submit("hardware", {"kind": c.kind, "name": r.get("name", ""), "props": r})

        # 磁盘健康计数与阵列降级数 → 缓存（告警引擎消费）
        disks = await volume_service.list_disks()
        failed = sum(1 for d in disks if d.get("health") == "failing")
        raid = await raid_service.raid_status()
        degraded = sum(1 for v in raid["software_raid"] + raid["hardware_raid"] if not v["healthy"])
        realtime_cache.set("disk_failed", failed, ttl=120)
        realtime_cache.set("raid_degraded", degraded, ttl=120)
        logger.debug("磁盘清单 %d 块（failing=%d），阵列降级 %d 卷", len(disks), failed, degraded)
    except Exception as exc:  # noqa: BLE001
        logger.warning("slow_tick 异常: %s", exc)
