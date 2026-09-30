"""5 秒级采集：温度 → 缓存；风扇调速输出（含告警引擎一轮评估）。"""

from __future__ import annotations

import logging

from app.db.session import session_factory
from app.services.alert.engine import evaluate_tick
from app.services.control import fan_manager
from app.services.monitor import temperature
from app.services.monitor.cache import realtime_cache

logger = logging.getLogger(__name__)


async def medium_tick() -> None:
    try:
        items = await temperature.temperatures()
        realtime_cache.set("temperatures", items, ttl=15)
        # 用最新温度修正最近一条原始点的 temp_max（存在才写）
        if items:
            from sqlalchemy import select, update

            from app.models.metrics import MetricPoint

            temp_max = temperature.max_celsius(items)
            async with session_factory() as db:
                latest = await db.execute(
                    select(MetricPoint.id)
                    .where(MetricPoint.granularity == "raw")
                    .order_by(MetricPoint.id.desc())
                    .limit(1)
                )
                row_id = latest.scalar_one_or_none()
                if row_id:
                    await db.execute(
                        update(MetricPoint).where(MetricPoint.id == row_id).values(temp_max=temp_max)
                    )
                await db.commit()

        # 风扇调速输出 + 结果回缓存（WS fans 事件源）
        async with session_factory() as db:
            outputs = await fan_manager.apply_tick(db)
            await db.commit()
        realtime_cache.set("fan_outputs", outputs, ttl=10)

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
        async with session_factory() as db:
            events = await evaluate_tick(db, ctx)
            await db.commit()
        if events:
            realtime_cache.set("latest_alert_events", events, ttl=10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("medium_tick 异常: %s", exc)
