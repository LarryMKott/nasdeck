"""告警引擎：阈值检测 + 持续时间计数 + 事件落库 + 渠道分发（5s tick 由 medium_5s 驱动）。

规则评估分三路，均把命中/恢复写为 alert_events 并按规则勾选渠道入队通知：
- 阈值规则（evaluate_tick，5s）：cpu_percent/mem_percent/temp_max/disk_temp/
  disk_failed/raid_degraded——后两者由慢采集刷新缓存；
- SMART 速率规则（evaluate_smart_rate_rules，15m，smart_15m 驱动）：
  metric=smart_rate:<指标>，7 天窗口增量按盘评估，事件键 rule_id:device；
- 容量预测规则（evaluate_capacity_rules，15m，volume_15m 驱动）：
  metric=capacity_forecast，days_to_full 按挂载点评估，事件键 rule_id:mount。

剧本动作（M2.1）：触发时规则 actions（fan_full/report）入队，drain 后台执行，
失败落「动作失败」一次性事件（rule_id=null）。

通知/动作与 DB 事务解耦：评估函数只入队（事务内零网络 IO），调用方提交事务
后经 schedule_drain 在后台 task 发送——慢渠道（email 15s 超时）不再拖住
SQLite 写锁与调度 tick。系统级事件（容器退出/巡检异常/阵列同步）无规则归属，
经 notify_broadcast 广播全部启用渠道。
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

# 剧本动作（M2.1 IF-THEN）：fan_full=风扇全速窗口（fan_manager 覆盖），report=生成诊断报告。
# 通知仍是 channels 多选（notify 天然是每条规则的基座动作）；actions 只承载额外动作。
VALID_ACTIONS = ("fan_full", "report")
_pending_actions: list[tuple[str, str, int]] = []  # (action, rule_name, event_id)


def channel_impl(channel_type: str):
    """按类型取渠道发送实现。

    Args:
        channel_type (str): 渠道类型，须为 CHANNEL_TYPES 白名单之一。

    Returns:
        BaseChannel: 对应渠道的发送实现。

    Raises:
        KeyError: 未注册的渠道类型。
    """
    if channel_type not in CHANNEL_TYPES:
        raise KeyError(channel_type)
    return _CHANNELS[channel_type]


def compare(value: float, comparator: str, threshold: float) -> bool:
    """按比较符判定指标值是否越过阈值。

    Args:
        value (float): 实际指标值。
        comparator (str): 比较符，支持 >、<、>=、<=、==。
        threshold (float): 规则阈值。

    Returns:
        bool: 命中返回 True；未知比较符一律 False（== 按 1e-9 容差判等）。
    """
    return {
        ">": value > threshold,
        "<": value < threshold,
        ">=": value >= threshold,
        "<=": value <= threshold,
        "==": abs(value - threshold) < 1e-9,
    }.get(comparator, False)


def metric_value(metric: str, ctx: dict) -> float | None:
    """从采集上下文取指标当前值。

    Args:
        metric (str): 指标名（cpu_percent/mem_percent/temp_max/disk_failed/
            raid_degraded）；disk_temp 特殊处理为取磁盘温度最大值。
        ctx (dict): 采集上下文，含 cpu_percent/mem_percent/temp_max/
            disk_failed/raid_degraded/disk_temps 键。

    Returns:
        float | None: 指标值；disk_temp 取 disk_temps 最大值（无数据返回
        None，该轮跳过评估），未知指标返回 None。
    """
    if metric == "disk_temp":
        temps = ctx.get("disk_temps") or []
        return max(temps) if temps else None
    return ctx.get(metric)


def _now() -> str:
    """当前 UTC 时间戳，用于事件 fired_at/resolved_at 字段。

    Returns:
        str: "%Y-%m-%dT%H:%M:%S+00:00" 格式的 UTC 时间戳。
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


async def reconcile_on_startup(db: AsyncSession) -> int:
    """启动对账：孤儿 firing 事件全部标记 resolved，事件流不悬挂。

    进程内 _firing 随上次进程消失，落库的 firing 事件成为孤儿
    （指标恢复后无人置 resolved）。

    Args:
        db (AsyncSession): 请求级会话（调用方 commit）。

    Returns:
        int: 标记 resolved 的事件条数。
    """
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
    按前缀清理；"{rule_id}:" 带冒号不会与其它规则 id 前缀混淆。

    Args:
        db (AsyncSession): 请求级会话（调用方 commit）。
        rule_id (int): 被删除的规则 id。
    """
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
    """阈值规则一轮评估（5s tick）：连续命中 duration_ticks 触发，恢复即置 resolved。

    命中/恢复的渠道通知只入队，不入库也不发送——见模块 docstring。

    Args:
        db (AsyncSession): 请求级会话（调用方 commit）。
        ctx (dict): 采集上下文，含 cpu_percent/mem_percent/temp_max/
            disk_failed/raid_degraded/disk_temps 键。

    Returns:
        list[dict]: 本轮触发/恢复的事件字典列表（WS alert 事件数据源）。
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
            _queue_actions(rule, event.id)

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

    Args:
        db (AsyncSession): 请求级会话（调用方 commit）。

    Returns:
        list[dict]: 本轮触发/恢复的事件字典列表。
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


async def evaluate_capacity_rules(db: AsyncSession, forecasts: list[dict]) -> list[dict]:
    """容量预测规则（metric=capacity_forecast）按挂载点评估：days_to_full 与阈值比较。

    由 volume_15m 采集任务驱动（15 分钟一格）。事件键 "{rule_id}:{mount}"——
    一规则可同时 fire 多个卷。与 smart_rate 不同：增速放缓后 days_to_full
    回升到阈值外（或归 None）会自然走恢复分支。

    Args:
        db (AsyncSession): 请求级会话（调用方 commit）。
        forecasts (list[dict]): 各挂载点写满预测，每项含 mount/days_to_full/
            last_percent 键。

    Returns:
        list[dict]: 本轮触发/恢复的事件字典列表。
    """
    result = await db.execute(
        select(AlertRule).where(AlertRule.enabled.is_(True), AlertRule.metric == "capacity_forecast")
    )
    rules = result.scalars().all()
    if not rules:
        return []
    enabled_channels = await _enabled_channels(db)
    forecast_map = {f["mount"]: f for f in forecasts}
    fired_events: list[dict] = []
    now = _now()

    for rule in rules:
        # 评估范围 = 有预测的卷 ∪ 正在 firing 的卷（卷消失/增速归零时走恢复分支）
        firing_mounts = {
            str(k).split(":", 1)[1]
            for k in _firing
            if isinstance(k, str) and k.startswith(f"{rule.id}:")
        }
        for mount in sorted(set(forecast_map) | firing_mounts):
            f = forecast_map.get(mount)
            days = f["days_to_full"] if f else None
            hit = days is not None and compare(days, rule.comparator, rule.threshold)
            key = f"{rule.id}:{mount}"
            count = _tick_counters.get(key, 0)
            count = count + 1 if hit else 0
            _tick_counters[key] = count

            message = (
                f"{rule.name}: {mount} 按当前增速约 {days:g} 天写满（已用 {f['last_percent'] if f else '?'}%）"
                if days is not None
                else f"{rule.name}: {mount} 无写满预测（增速≈0 或数据不足）"
            )
            if hit and count >= rule.duration_ticks and key not in _firing:
                event = AlertEvent(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    metric=rule.metric,
                    value=days,
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
                        title=f"告警恢复 · {rule.name}", body=f"{mount} 写满预测已回到阈值内",
                    )
    return fired_events


async def _enabled_channels(db: AsyncSession) -> dict[int, AlertChannel]:
    """查询全部启用渠道。

    Args:
        db (AsyncSession): 请求级会话。

    Returns:
        dict[int, AlertChannel]: 渠道 id → 渠道对象。
    """
    result = await db.execute(select(AlertChannel).where(AlertChannel.enabled.is_(True)))
    return {c.id: c for c in result.scalars()}


async def notify_broadcast(db: AsyncSession, title: str, body: str) -> None:
    """向全部启用渠道广播（容器退出/巡检异常等系统级事件，无规则归属）。

    Args:
        db (AsyncSession): 请求级会话。
        title (str): 通知标题。
        body (str): 通知正文。
    """
    channels = await _enabled_channels(db)
    _queue_notify(channels, list(channels.keys()), title=title, body=body)


def _queue_notify(channels: dict[int, AlertChannel], channel_ids: list[int], title: str, body: str) -> None:
    """按规则勾选的渠道把待发通知入队（事务内零网络 IO）。

    Args:
        channels (dict[int, AlertChannel]): 启用渠道映射（_enabled_channels 结果）。
        channel_ids (list[int]): 规则勾选的渠道 id 列表。
        title (str): 通知标题。
        body (str): 通知正文。
    """
    for channel_id in channel_ids or []:
        channel = channels.get(channel_id)
        if channel:
            _pending.append((channel.type, dict(channel.config), title, body))


def _queue_actions(rule: AlertRule, event_id: int) -> None:
    """把规则的剧本动作入队（只收 VALID_ACTIONS 白名单内的动作）。

    Args:
        rule (AlertRule): 触发的规则，取其 actions 列表。
        event_id (int): 关联事件 id（动作失败落库时引用）。
    """
    for action in rule.actions or []:
        if action in VALID_ACTIONS:
            _pending_actions.append((action, rule.name, event_id))


async def _execute_action(action: str, rule_name: str, event_id: int) -> None:
    """剧本动作执行（drain 后台 task，事务外）：失败落一条一次性告警事件，不中断其余动作。

    Args:
        action (str): 动作名，fan_full 或 report。
        rule_name (str): 触发规则名（失败事件引用）。
        event_id (int): 关联事件 id（仅日志引用）。
    """
    try:
        if action == "fan_full":
            from app.services.control import fan_manager

            fan_manager.request_full_speed()
        elif action == "report":
            from app.services.report import diagnostic

            await diagnostic.generate_diagnostic(redact=True)
        else:  # _queue_actions 已过滤，防御分支
            return
    except Exception as exc:  # noqa: BLE001 动作失败可见但不拖垮通知/调度
        logger.warning("剧本动作失败 %s（rule=%s event=%s）: %s", action, rule_name, event_id, exc)
        try:
            from app.db.session import session_factory

            async with session_factory() as db:
                now = _now()
                db.add(
                    AlertEvent(
                        rule_id=None,
                        rule_name=f"动作失败 · {rule_name}",
                        metric=f"action:{action}",
                        value=None,
                        threshold=None,
                        severity="warning",
                        status="resolved",
                        message=str(exc)[:200],
                        fired_at=now,
                        resolved_at=now,
                    )
                )
                await db.commit()
        except Exception as exc2:  # noqa: BLE001 连事件库都写不进只剩日志
            logger.error("动作失败事件落库失败: %s", exc2)


def schedule_drain() -> None:
    """事务提交后由调用方触发：后台 task 发送待发通知与待执行动作。

    上一批尚未发完（多渠道叠加 10-15s 超时）时直接跳过本轮入队——队列在
    evaluate_tick 后持续累积，不会丢通知，只合并发送时机。

    通知与 DB 事务解耦：必须由调用方在事务提交后触发，否则后台 drain
    可能读到未提交数据。
    """
    global _drain_task
    if not _pending and not _pending_actions:
        return
    if _drain_task is not None and not _drain_task.done():
        return
    _drain_task = asyncio.create_task(_drain())


async def _drain() -> None:
    """后台 drain：先逐条发送待发通知，再依次执行待执行剧本动作。

    单条失败只记日志不抛出，不阻断队列（通知失败不阻断引擎，
    动作失败落一次性事件）。
    """
    while _pending:
        channel_type, config, title, body = _pending.pop(0)
        try:
            ok = await channel_impl(channel_type).send(config, title, body)
        except Exception as exc:  # noqa: BLE001 通知失败不阻断引擎
            logger.warning("通知发送失败 channel=%s: %s", channel_type, exc)
            ok = False
        logger.info("通知 %s channel=%s ok=%s", title, channel_type, ok)
    while _pending_actions:
        action, rule_name, event_id = _pending_actions.pop(0)
        await _execute_action(action, rule_name, event_id)


def event_dict(event: AlertEvent) -> dict:
    """AlertEvent ORM 实例转可 JSON 序列化的事件字典。

    Args:
        event (AlertEvent): 事件 ORM 实例。

    Returns:
        dict: 含 id/rule_id/rule_name/metric/value/threshold/severity/
        status/message/fired_at/resolved_at 键。
    """
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
