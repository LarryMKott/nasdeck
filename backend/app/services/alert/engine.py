"""告警引擎：阈值检测 + 持续时间计数 + 事件落库 + 渠道分发（5s tick 由 medium_5s 驱动）。

metric 取值来源：实时快照（cpu_percent/mem_percent）、温度 max（temp_max）、
磁盘失败计数（disk_failed）、阵列降级数（raid_degraded）——后两者由慢采集刷新。
另有一类慢速规则 smart_rate:<指标>（SMART 变化速率，7 天窗口）由 smart_15m
采集任务驱动 evaluate_smart_rate_rules 评估——事件键 rule_id:device，同一规则
可同时 fire 多块盘。

通知发送与 DB 事务解耦：evaluate_tick 只把待发通知入队（事务内零网络 IO），
调用方提交事务后经 schedule_drain 在后台 task 发送——慢渠道（email 15s 超时）
不再拖住 SQLite 写锁与 5s 调度 tick。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertChannel, AlertEvent, AlertRule
from app.services.alert.channels.bark import BarkChannel
from app.services.alert.channels.base import CHANNEL_TYPES
from app.services.alert.channels.email import EmailChannel
from app.services.alert.channels.telegram import TelegramChannel
from app.services.alert.channels.webhook import WebhookChannel
from app.services.storage import smart_history

logger = logging.getLogger(__name__)

_CHANNELS = {c.type: c for c in (TelegramChannel(), BarkChannel(), EmailChannel(), WebhookChannel())}

# 进程内连击计数：rule_id → 连续满足次数
_tick_counters: dict[int, int] = {}
# rule_id → 活跃事件 id（用于恢复）
_firing: dict[int, int] = {}

# 待发通知队列：(channel_type, config, title, body)——事务内只入队
_pending: list[tuple[str, dict, str, str]] = []
_drain_task: asyncio.Task | None = None


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


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


async def reconcile_on_startup(db: AsyncSession) -> int:
    """启动对账：进程内 _firing 随上次进程消失，落库的 firing 事件成为孤儿
    （指标恢复后无人置 resolved）。全部标记 resolved，事件流不悬挂。"""
    result = await db.execute(select(AlertEvent).where(AlertEvent.status == "firing"))
    orphans = result.scalars().all()
    now = _now()
    for event in orphans:
        event.status = "resolved"
        event.resolved_at = now
    if orphans:
        await db.flush()
        logger.warning("启动对账：上次进程遗留 %s 条 firing 事件已标记 resolved", len(orphans))
    return len(orphans)


async def resolve_rule_events(db: AsyncSession, rule_id: int) -> None:
    """删除规则时收尾其活跃事件，避免事件流悬挂 firing（rule_id 已无主）。

    计数键含设备后缀（smart_rate 规则一格多盘："{rule_id}:{device}"），
    按前缀清理；"{rule_id}:" 带冒号不会与其它规则 id 前缀混淆。"""
    for key in [k for k in _tick_counters if k == rule_id or str(k).startswith(f"{rule_id}:")]:
        _tick_counters.pop(key, None)
    for key in [k for k in _firing if k == rule_id or str(k).startswith(f"{rule_id}:")]:
        _firing.pop(key, None)
    result = await db.execute(select(AlertEvent).where(AlertEvent.rule_id == rule_id, AlertEvent.status == "firing"))
    now = _now()
    count = 0
    for event in result.scalars():
        event.status = "resolved"
        event.resolved_at = now
        count += 1
    if count:
        await db.flush()


async def evaluate_tick(db: AsyncSession, ctx: dict) -> list[dict]:
    """一轮评估，返回本轮触发/恢复的事件（WS alert 事件数据源）。

    命中/恢复的渠道通知只入队，不入库也不发送——见模块 docstring。
    """
    now = _now()
    result = await db.execute(select(AlertRule).where(AlertRule.enabled.is_(True)))
    rules = result.scalars().all()
    enabled_channels = await _enabled_channels(db)
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
            fired_events.append(event_dict(event))
            _queue_notify(enabled_channels, rule.channels, title=f"告警触发 · {rule.name}", body=message)

        elif not hit and rule.id in _firing:
            event_id = _firing.pop(rule.id)
            event = await db.get(AlertEvent, event_id)
            if event:
                event.status = "resolved"
                event.resolved_at = now
                fired_events.append(event_dict(event))
                _queue_notify(
                    enabled_channels, rule.channels,
                    title=f"告警恢复 · {rule.name}", body=f"{rule.metric} 已回落正常",
                )
    return fired_events


async def evaluate_smart_rate_rules(db: AsyncSession) -> list[dict]:
    """SMART 变化速率规则（metric=smart_rate:<指标>，7 天窗口）按设备评估增量。

    由 smart_15m 采集任务驱动（15 分钟一格）：从 1d 桶取窗口首末点算 delta，
    与阈值比较。事件键 "{rule_id}:{device}"——同一规则可同时 fire 多块盘。
    计数器类指标增量不会回落，事件保持 firing 至规则删除（resolve_rule_events 收尾）；
    旧点滑出窗口使 delta 缩回阈值内时照常走恢复分支。
    """
    result = await db.execute(select(AlertRule).where(AlertRule.enabled.is_(True)))
    rules = [r for r in result.scalars() if r.metric.startswith("smart_rate:")]
    if not rules:
        return []
    enabled_channels = await _enabled_channels(db)
    fired_events: list[dict] = []
    by_metric: dict[str, list[AlertRule]] = {}
    for rule in rules:
        by_metric.setdefault(rule.metric.split(":", 1)[1], []).append(rule)

    now = _now()
    for metric_name, metric_rules in by_metric.items():
        deltas = {d["device"]: d for d in await smart_history.rate_deltas(db, metric_name)}
        for rule in metric_rules:
            # 评估范围 = 有窗口增量的盘 ∪ 正在 firing 的盘：盘数据滑出窗口
            # （删除/换盘）时走恢复分支，事件不悬挂
            firing_devices = {
                str(k).split(":", 1)[1]
                for k in _firing
                if isinstance(k, str) and k.startswith(f"{rule.id}:")
            }
            for device in sorted(set(deltas) | firing_devices):
                d = deltas.get(device)
                hit = compare(d["delta"], rule.comparator, rule.threshold) if d else False
                key = f"{rule.id}:{device}"
                count = _tick_counters.get(key, 0)
                count = count + 1 if hit else 0
                _tick_counters[key] = count

                message = (
                    f"{rule.name}: {device} {metric_name} {smart_history.RATE_WINDOW_DAYS} 天 "
                    f"{d['old']:g} → {d['new']:g}（Δ{d['delta']:+g}）"
                    if d
                    else f"{rule.name}: {device} {metric_name} 窗口内无数据"
                )
                if hit and count >= rule.duration_ticks and key not in _firing:
                    event = AlertEvent(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        metric=rule.metric,
                        value=d["delta"],
                        threshold=rule.threshold,
                        severity=rule.severity,
                        status="firing",
                        message=message,
                        fired_at=now,
                    )
                    db.add(event)
                    await db.flush()
                    _firing[key] = event.id
                    fired_events.append(event_dict(event))
                    _queue_notify(
                        enabled_channels, rule.channels,
                        title=f"告警触发 · {rule.name}", body=message,
                    )
                elif not hit and key in _firing:
                    event = await db.get(AlertEvent, _firing.pop(key))
                    if event:
                        event.status = "resolved"
                        event.resolved_at = now
                        fired_events.append(event_dict(event))
                        _queue_notify(
                            enabled_channels, rule.channels,
                            title=f"告警恢复 · {rule.name}", body=f"{device} {metric_name} 变化已回落阈值内",
                        )
    return fired_events


async def _enabled_channels(db: AsyncSession) -> dict[int, AlertChannel]:
    result = await db.execute(select(AlertChannel).where(AlertChannel.enabled.is_(True)))
    return {c.id: c for c in result.scalars()}


def _queue_notify(channels: dict[int, AlertChannel], channel_ids: list[int], title: str, body: str) -> None:
    for channel_id in channel_ids or []:
        channel = channels.get(channel_id)
        if channel:
            _pending.append((channel.type, dict(channel.config), title, body))


def schedule_drain() -> None:
    """事务提交后由调用方触发：后台 task 发送待发通知。

    上一批尚未发完（多渠道叠加 10-15s 超时）时直接跳过本轮入队——队列在
    evaluate_tick 后持续累积，不会丢通知，只合并发送时机。
    """
    global _drain_task
    if not _pending:
        return
    if _drain_task is not None and not _drain_task.done():
        return
    _drain_task = asyncio.create_task(_drain())


async def _drain() -> None:
    while _pending:
        channel_type, config, title, body = _pending.pop(0)
        try:
            ok = await channel_impl(channel_type).send(config, title, body)
        except Exception as exc:  # noqa: BLE001 通知失败不阻断引擎
            logger.warning("通知发送失败 channel=%s: %s", channel_type, exc)
            ok = False
        logger.info("通知 %s channel=%s ok=%s", title, channel_type, ok)


def event_dict(event: AlertEvent) -> dict:
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
