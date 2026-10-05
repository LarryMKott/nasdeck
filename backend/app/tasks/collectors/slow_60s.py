"""60 秒级采集：硬件信息落库（SMART 依赖 smartctl，不可用即跳过）+ 磁盘/阵列健康刷新
+ 容器退出检测 + 阵列同步活动转换。

后两段各自独立 try/except：docker/探测不可用时返回空，绝不拖垮上段硬件采集。
"""

from __future__ import annotations

import logging

from app.db import ingest
from app.db.session import session_factory
from app.services.alert import engine as alert_engine
from app.services.hardware.cpu import CpuCollector
from app.services.hardware.gpu import GpuCollector
from app.services.hardware.memory import MemoryCollector
from app.services.hardware.motherboard import MotherboardCollector
from app.services.hardware.nic import NicCollector
from app.services.hardware.raid_card import RaidCardCollector
from app.services.monitor import temperature
from app.services.monitor.cache import realtime_cache
from app.services.storage import raid as raid_service
from app.services.storage import sync_watch
from app.services.storage import volumes as volume_service
from app.services.system import docker_watch, port_watch

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
    """60 秒一轮：硬件清单落库 + 磁盘/阵列健康刷新 + 容器退出检测 + 阵列同步活动转换。

    首段：6 个硬件采集器 safe_collect → ingest 通道投递 hardware 行（SMART
    依赖 smartctl，不可用即对应采集器自行降级）；次段：磁盘清单 + SMART 健康
    计数、阵列降级数写 realtime_cache（告警引擎消费，健康来自 temperature.disk_health
    同一轮 60s 缓存）。后两段各自独立 try/except：docker/探测不可用时返回空，
    绝不拖垮上段硬件采集；任何异常只记 warning，不中断调度。
    """
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

        # 磁盘健康计数与阵列降级数 → 缓存（告警引擎消费）。
        # health 来自 SMART 扫描（temperature.disk_health，与盘温同一轮 60s 缓存）：
        # list_disks(lsblk) 本身不带健康字段，旧实现 get("health") 恒 None → 指标恒 0
        disks = await volume_service.list_disks()
        health_map = await temperature.disk_health()
        failed = sum(1 for d in disks if health_map.get(d.get("device")) == "failing")
        raid = await raid_service.raid_status()
        degraded = sum(1 for v in raid["software_raid"] + raid["hardware_raid"] if not v["healthy"])
        realtime_cache.set("disk_failed", failed, ttl=120)
        realtime_cache.set("disk_health", health_map, ttl=120)
        realtime_cache.set("raid_degraded", degraded, ttl=120)
        logger.debug("磁盘清单 %d 块（failing=%d），阵列降级 %d 卷", len(disks), failed, degraded)
    except Exception as exc:  # noqa: BLE001
        logger.warning("slow_tick 异常: %s", exc)

    # 容器退出检测（独立段：docker 不可用 watch_tick 返回空，不影响上段）
    try:
        exits = await docker_watch.watch_tick()
        if exits:
            async with session_factory() as db:
                await docker_watch.persist_and_notify(db, exits)
                await db.commit()
            alert_engine.schedule_drain()
            realtime_cache.set("docker_exits", exits, ttl=120)
            logger.warning("容器退出 %d 个：%s", len(exits), "; ".join(e["name"] for e in exits))
    except Exception as exc:  # noqa: BLE001
        logger.warning("docker_watch 异常: %s", exc)

    # 监听端口异动（安全哨兵：新端口且无标注 → 事件 + 广播；24h 去重）
    try:
        async with session_factory() as db:
            port_events = await port_watch.watch_tick(db)
            if port_events:
                await port_watch.persist_and_notify(db, port_events)
                await db.commit()
                alert_engine.schedule_drain()
                realtime_cache.set("port_events", port_events, ttl=120)
                logger.warning("新增监听端口 %d 个：%s", len(port_events), port_events)
    except Exception as exc:  # noqa: BLE001
        logger.warning("port_watch 异常: %s", exc)

    # 阵列同步/重建活动转换（开始广播 warning，结束仅记 info 事件）
    try:
        transitions = await sync_watch.detect_sync_transitions()
        if transitions:
            from datetime import UTC, datetime

            from app.models.alert import AlertEvent

            now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")

            async with session_factory() as db:
                for t in transitions:
                    started = t["phase"] == "started"
                    message = (
                        f"阵列 {t['name']} 开始{t['action']}（多由降级重建引发，进度见存储卷页）"
                        if started
                        else f"阵列 {t['name']} {t['action']} 完成"
                    )
                    db.add(
                        AlertEvent(
                            rule_id=None,
                            rule_name="阵列同步",
                            metric="raid_sync",
                            value=None,
                            threshold=None,
                            severity="warning" if started else "info",
                            status="resolved",
                            message=message,
                            fired_at=now,
                            resolved_at=now,
                        )
                    )
                    if started:
                        await alert_engine.notify_broadcast(db, title=f"阵列同步开始 · {t['name']}", body=message)
                await db.commit()
            if any(t["phase"] == "started" for t in transitions):
                alert_engine.schedule_drain()
            realtime_cache.set("raid_sync_events", transitions, ttl=120)
    except Exception as exc:  # noqa: BLE001
        logger.warning("sync_watch 异常: %s", exc)
