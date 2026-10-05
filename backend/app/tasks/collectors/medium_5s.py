"""5 秒级采集：温度 → 缓存（fast_tick 落库时内嵌，不再回填 UPDATE）；风扇调速 + 告警评估。

一轮顺序：温度缓存 → 时段静音计划缓存刷新（30s TTL 限流读库）→ 风扇调速输出
+ 告警评估同事务（一次 commit 一次 fsync，真机跳秒修复的另一环）→ 通知后台
drain → GPU 采样缓存。
"""

from __future__ import annotations

import logging

from app.db.session import session_factory
from app.services.alert.engine import evaluate_tick, schedule_drain
from app.services.control import fan_manager
from app.services.monitor import gpu as gpu_service
from app.services.monitor import temperature
from app.services.monitor.cache import realtime_cache

logger = logging.getLogger(__name__)


async def medium_tick() -> None:
    """5 秒一轮：温度缓存 → 风扇调速 + 告警评估同事务 → 通知后台 drain → GPU 采样缓存。

    温度写 realtime_cache 供 fast_tick 落库时内嵌（不再回填 UPDATE）；
    风扇调速输出与告警评估共用一个事务（一次 commit 一次 fsync，真机跳秒
    修复的另一环），时段静音计划缓存刷新带 30s TTL 限流读库；事务提交后
    通知交后台 task 发送，慢渠道不再占住 SQLite 写锁与 5s 调度。
    任何异常只记 warning，不中断调度。
    """
    try:
        items = await temperature.temperatures()
        realtime_cache.set("temperatures", items, ttl=15)
        if items:
            logger.debug(
                "温度采集 %d 点（芯片: %s）max=%.1fC",
                len(items),
                ",".join(sorted({t["chip"] for t in items})),
                temperature.max_celsius(items) or 0.0,
            )
        # 风扇调速输出 + 告警评估同事务，一次 commit 一次 fsync（真机跳秒修复的另一环）
        await fan_manager.refresh_schedule_cache()  # 时段静音计划缓存（30s TTL 限流读库）
        async with session_factory() as db:
            outputs = await fan_manager.apply_tick(db)

            # 告警评估上下文
            snap = realtime_cache.get("realtime") or {}
            disk_temps = [t["celsius"] for t in items if t["zone"] in ("disk", "nvme")]
            ctx = {
                "cpu_percent": snap.get("cpu_percent"),
                "mem_percent": snap.get("mem_percent"),
                "temp_max": temperature.max_celsius(items),
                "disk_temps": disk_temps,
                "disk_failed": realtime_cache.get("disk_failed"),
                "raid_degraded": realtime_cache.get("raid_degraded"),
            }
            events = await evaluate_tick(db, ctx)
            await db.commit()

        # 事务已提交：通知经后台 task 发送（慢渠道不再占住 SQLite 写锁与 5s 调度）
        schedule_drain()

        # GPU 实时分量（服务内 5s 采样缓存；fast_tick 落库 gpu 列与 realtime 快照读取该缓存）
        realtime_cache.set("gpu", await gpu_service.collect(), ttl=10)
        realtime_cache.set("fan_outputs", outputs, ttl=10)
        if events:
            realtime_cache.set("latest_alert_events", events, ttl=10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("medium_tick 异常: %s", exc)
