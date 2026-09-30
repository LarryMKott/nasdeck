"""告警引擎：阈值检测 + 持续时间计数 + 事件落库 + 渠道分发（5s tick 由 medium_5s 驱动）。

metric 取值来源：实时快照（cpu_percent/mem_percent）、温度 max（temp_max）、
磁盘失败计数（disk_failed）、阵列降级数（raid_degraded）——后两者由慢采集刷新。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertChannel, AlertEvent, AlertRule
from app.services.alert.channels.bark import BarkChannel
from app.services.alert.channels.base import CHANNEL_TYPES
from app.services.alert.channels.email import EmailChannel
from app.services.alert.channels.telegram import TelegramChannel

logger = logging.getLogger(__name__)

_CHANNELS = {c.type: c for c in (TelegramChannel(), BarkChannel(), EmailChannel())}

# 进程内连击计数：rule_id → 连续满足次数
_tick_counters: dict[int, int] = {}
# rule_id → 活跃事件 id（用于恢复）
_firing: dict[int, int] = {}


def channel_impl(channel_type: str):
    if channel_type not in CHANNEL_TYPES:
        raise KeyError(channel_type)
    return _CHANNELS[channel_type]


def compare(value: float, comparator: str, threshold: float) -> bool:
    return {
        ">": value > threshold,
        "<": value < threshold,
        ">=": value >= threshold,
        "<=": value <= threshold,
        "==": abs(value - threshold) < 1e-9,
    }.get(comparator, False)


def metric_value(metric: str, ctx: dict) -> float | None:
    """ctx: {cpu_percent, mem_percent, temp_max, disk_failed, raid_degraded, disk_temps}"""
    if metric == "disk_temp":
        temps = ctx.get("disk_temps") or []
        return max(temps) if temps else None
    return ctx.get(metric)


async def evaluate_tick(db: AsyncSession, ctx: dict) -> list[dict]:
    """一轮评估，返回本轮触发/恢复的事件（WS alert 事件数据源）。"""
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    result = await db.execute(select(AlertRule).where(AlertRule.enabled.is_(True)))
    rules = result.scalars().all()
    fired_events = []

    for rule in rules:
        value = metric_value(rule.metric, ctx)
        if value is None:
            continue
        hit = compare(value, rule.comparator, rule.threshold)
        count = _tick_counters.get(rule.id, 0)
        count = count + 1 if hit else 0
        _tick_counters[rule.id] = count

        if hit and count >= rule.duration_ticks and rule.id not in _firing:
            message = f"{rule.name}: {rule.metric}={value} {rule.comparator} {rule.threshold}"
            event = AlertEvent(
                rule_id=rule.id,
                rule_name=rule.name,
                metric=rule.metric,
                value=value,
                threshold=rule.threshold,
                severity=rule.severity,
                status="firing",
                message=message,
                fired_at=now,
            )
            db.add(event)
            await db.flush()
            _firing[rule.id] = event.id
            fired_events.append(_event_dict(event))
            await _notify(db, rule, title=f"告警触发 · {rule.name}", body=message)

        elif not hit and rule.id in _firing:
            event_id = _firing.pop(rule.id)
            event = await db.get(AlertEvent, event_id)
            if event:
                event.status = "resolved"
                event.resolved_at = now
                fired_events.append(_event_dict(event))
                await _notify(db, rule, title=f"告警恢复 · {rule.name}", body=f"{rule.metric} 已回落正常")
    return fired_events


async def _notify(db: AsyncSession, rule: AlertRule, title: str, body: str) -> None:
    if not rule.channels:
        return
    result = await db.execute(select(AlertChannel).where(AlertChannel.enabled.is_(True)))
    by_id = {c.id: c for c in result.scalars()}
    for channel_id in rule.channels:
        channel = by_id.get(channel_id)
        if not channel:
            continue
        try:
            impl = channel_impl(channel.type)
            ok = await impl.send(channel.config, title, body)
        except Exception as exc:  # noqa: BLE001 通知失败不阻断引擎
            logger.warning("通知发送失败 channel=%s: %s", channel_id, exc)
            ok = False
        logger.info("通知 %s channel=%s ok=%s", title, channel_id, ok)


def _event_dict(event: AlertEvent) -> dict:
    return {
        "id": event.id,
        "rule_id": event.rule_id,
        "rule_name": event.rule_name,
        "metric": event.metric,
        "value": event.value,
        "threshold": event.threshold,
        "severity": event.severity,
        "status": event.status,
        "message": event.message,
        "fired_at": event.fired_at,
        "resolved_at": event.resolved_at,
    }
