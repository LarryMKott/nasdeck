"""15 分钟级容量趋势采集：psutil 枚举挂载点（零 fork）→ 1h 桶落库 → 写满预测规则评估。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.db.session import session_factory
from app.services.alert.engine import evaluate_capacity_rules, schedule_drain
from app.services.monitor.cache import realtime_cache
from app.services.storage import capacity
from app.services.storage import volumes as volume_service

logger = logging.getLogger(__name__)

_last_day: str | None = None


async def volume_15m_tick() -> None:
    """15 分钟一轮容量趋势：枚举挂载点 → 1h 桶落库 → 写满预测 + 规则评估。

    psutil 枚举挂载点零 fork；跨 UTC 日时顺带执行一次保留窗清理
    （_last_day 翻日标记保证每日一跑）。有新告警事件时写 realtime_cache
    并调度后台通知 drain。任何异常只记 warning，不中断调度。
    """
    global _last_day
    try:
        volumes = volume_service.list_volumes()
        async with session_factory() as db:
            n = await capacity.record_snapshots(db, volumes)
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            if _last_day != today:
                await capacity.prune_old(db)
                _last_day = today
            forecasts = await capacity.forecast_all(db)
            events = await evaluate_capacity_rules(db, forecasts)
            await db.commit()
        if events:
            realtime_cache.set("latest_alert_events", events, ttl=600)
        schedule_drain()
        logger.debug("容量趋势 %d 卷 %d 点（forecasts=%d, events=%d）", len(volumes), n, len(forecasts), len(events))
    except Exception as exc:  # noqa: BLE001
        logger.warning("volume_15m 异常: %s", exc)
