"""15 分钟级 SMART 趋势采集：smartctl 逐盘串行 → 1h/1d 桶落库 → 变化速率规则评估。

SMART 查询是重 fork（smartctl -a 每盘数百毫秒，-n standby 不打扰休眠盘），
独立 15m 任务不进 1s/5s/60s 快车道（低占用采集架构约定）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.db.session import session_factory
from app.services.alert.engine import evaluate_smart_rate_rules, schedule_drain
from app.services.monitor.cache import realtime_cache
from app.services.storage import smart as smart_service
from app.services.storage import smart_history
from app.services.storage import volumes as volume_service

logger = logging.getLogger(__name__)

# UTC 日期翻日标记：保留窗清理每日一跑即可
_last_day: str | None = None


async def smart_15m_tick() -> None:
    """15 分钟一轮 SMART 趋势：逐盘串行采样 → 1h/1d 桶落库 → 变化速率规则评估。

    逐盘独立 try/except，单盘失败不拖累其余盘；跨 UTC 日时顺带执行一次
    保留窗清理（_last_day 翻日标记保证每日一跑）。有新告警事件时写
    realtime_cache 并调度后台通知 drain。任何异常只记 warning，不中断调度。
    """
    global _last_day
    try:
        disks = await volume_service.list_disks()
        devices = sorted({smart_history.smart_key(d.get("device") or "") for d in disks if d.get("device")})
        reports = []
        for dev in devices:
            try:
                reports.append(await smart_service.smart_report(dev))
            except Exception as exc:  # noqa: BLE001 单盘失败不拖累其余盘
                logger.warning("SMART 趋势采集失败 %s: %s", dev, exc)

        async with session_factory() as db:
            n = await smart_history.record_snapshots(db, reports)
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            if _last_day != today:
                await smart_history.prune_old(db)
                _last_day = today
            events = await evaluate_smart_rate_rules(db)
            await db.commit()
        if events:
            realtime_cache.set("latest_alert_events", events, ttl=600)
        schedule_drain()
        logger.debug("SMART 趋势采集 %d 盘 %d 点（events=%d）", len(reports), n, len(events))
    except Exception as exc:  # noqa: BLE001
        logger.warning("smart_15m 异常: %s", exc)
