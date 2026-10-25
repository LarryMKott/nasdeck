"""告警引擎：阈值检测 + 持续时间计数 + 事件落库 + 渠道分发（5s tick 由 medium_5s 驱动）。

metric 取值来源：实时快照（cpu_percent/mem_percent）、温度 max（temp_max）、
磁盘失败计数（disk_failed）、阵列降级数（raid_degraded）——后两者由慢采集刷新。

通知发送与 DB 事务解耦：evaluate_tick 只把待发通知入队（事务内零网络 IO），
调用方提交事务后经 schedule_drain 在后台 task 发送——慢渠道（email 15s 超时）
不再拖住 SQLite 写锁与 5s 调度 tick。
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertChannel, AlertEvent, AlertRule
from app.services.alert.channels.bark import BarkChannel
from app.services.alert.channels.base import CHANNEL_TYPES
from app.services.alert.channels.email import EmailChannel
from app.services.alert.channels.telegram import TelegramChannel
from app.services.alert.channels.webhook import WebhookChannel

logger = logging.getLogger(__name__)

_CHANNELS = {c.type: c for c in (TelegramChannel(), BarkChannel(), EmailChannel(), WebhookChannel())}

# 进程内连击计数：rule_id → 连续满足次数
_tick_counters: dict[int, int] = {}
# rule_id → 活跃事件 id（用于恢复）
_firing: dict[int, int] = {}

# 待发通知队列（事务内只入队，原型 C1）：
# {channel_id, channel_type, config, title, body, attempts}——失败重试 ≤3 次
# （重入队到尾部，被后续条目天然隔开形成退避），超限丢弃并在渠道健康留痕
_PENDING_MAX = 200
_RETRY_MAX = 3
_pending: list[dict] = []
_drain_task: asyncio.Task | None = None
# 渠道健康（原型 C1/C2，UI 渠道卡与自检页消费）
_channel_health: dict[int, dict] = {}


def _new_health() -> dict:
    return {"send_failures": 0, "last_error": None, "last_ok_ts": None, "last_attempt_ts": None, "overflow_dropped": 0}


def channel_health() -> dict[int, dict]:
    """各渠道最近发送结果快照。"""
    return {cid: dict(h) for cid, h in _channel_health.items()}


def pending_stats() -> dict:
    return {"depth": len(_pending), "capacity": _PENDING_MAX}


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
    """删除规则时收尾其活跃事件，避免事件流悬挂 firing（rule_id 已无主）。"""
    _tick_counters.pop(rule_id, None)
    _firing.pop(rule_id, None)
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
        try:
            fired_events.extend(await _evaluate_rule(db, rule, ctx, enabled_channels, now))
        except Exception as exc:  # noqa: BLE001 单规则失败只跳过自身，不中断整轮（原型 C1）
            logger.warning("规则 %s(%s) 评估异常，跳过本轮: %s", rule.id, rule.name, exc, exc_info=True)
    return fired_events


async def _evaluate_rule(
    db: AsyncSession, rule: AlertRule, ctx: dict, enabled_channels: dict[int, AlertChannel], now: str
) -> list[dict]:
    fired_events = []
    value = metric_value(rule.metric, ctx)
    if value is None:
        return fired_events
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


async def _enabled_channels(db: AsyncSession) -> dict[int, AlertChannel]:
    result = await db.execute(select(AlertChannel).where(AlertChannel.enabled.is_(True)))
    return {c.id: c for c in result.scalars()}


def _queue_notify(channels: dict[int, AlertChannel], channel_ids: list[int], title: str, body: str) -> None:
    for channel_id in channel_ids or []:
        channel = channels.get(channel_id)
        if not channel:
            continue
        if len(_pending) >= _PENDING_MAX:
            # 队列上限：慢渠道叠加抖动规则时不再无限累积；丢弃留痕于渠道健康（原型 C1）
            h = _channel_health.setdefault(channel_id, _new_health())
            h["overflow_dropped"] += 1
            logger.warning("通知队列已满（%d），丢弃 channel=%s 的通知", _PENDING_MAX, channel.type)
            continue
        _pending.append(
            {
                "channel_id": channel_id,
                "channel_type": channel.type,
                "config": dict(channel.config),
                "title": title,
                "body": body,
                "attempts": 0,
            }
        )


def schedule_drain() -> None:
    """事务提交后由调用方触发：后台 task 发送待发通知。

    上一批尚未发完（多渠道叠加 10-15s 超时）时直接跳过本轮调度——队列在
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
        item = _pending.pop(0)
        cid = item["channel_id"]
        health = _channel_health.setdefault(cid, _new_health())
        health["last_attempt_ts"] = time.time()
        try:
            error = await channel_impl(item["channel_type"]).send(
                item["config"], item["title"], item["body"]
            )
        except Exception as exc:  # noqa: BLE001 通知失败不阻断引擎
            logger.warning("通知发送异常 channel=%s: %s", item["channel_type"], exc)
            error = "network"
        if error is None:
            health.update(send_failures=0, last_error=None, last_ok_ts=time.time())
            logger.info("通知已发送 channel=%s(%s)", item["channel_type"], cid)
            continue
        item["attempts"] += 1
        if item["attempts"] < _RETRY_MAX:
            # 重入队到尾部：被后续条目隔开，天然形成重试间隔（原型 C1）
            _pending.append(item)
            logger.info("通知发送失败（%s）channel=%s(%s)，第 %d 次重试入队", error, item["channel_type"], cid, item["attempts"])
            continue
        health["send_failures"] += 1
        health["last_error"] = error
        logger.warning(
            "通知重试 %d 次仍失败 channel=%s(%s)，已放弃（错误码 %s）", _RETRY_MAX, item["channel_type"], cid, error
        )


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
