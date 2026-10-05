"""告警接口（契约 §3.5）。"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiKeyDep, DbDep, TrimAuthDep
from app.core.exceptions import InvalidParamsError, NotFoundError
from app.models.alert import AlertChannel, AlertEvent, AlertRule
from app.schemas.alert import (
    AlertChannelIn,
    AlertChannelItem,
    AlertEventItem,
    AlertRuleIn,
    AlertRuleItem,
    ChannelTestResult,
)
from app.services.alert import engine
from app.services.alert.channels.base import mask_config

router = APIRouter(prefix="/alert", tags=["alert"], dependencies=[ApiKeyDep, TrimAuthDep])


def _rule_dict(rule: AlertRule) -> dict:
    """将告警规则 ORM 行转为 API 输出字典。

    Args:
        rule (AlertRule): 告警规则 ORM 对象。

    Returns:
        dict: 规则字段字典，形状见契约 §3.5 AlertRuleItem。
    """
    return {
        "id": rule.id,
        "name": rule.name,
        "metric": rule.metric,
        "comparator": rule.comparator,
        "threshold": rule.threshold,
        "duration_ticks": rule.duration_ticks,
        "severity": rule.severity,
        "channel_ids": rule.channels,
        "actions": rule.actions or [],
        "enabled": rule.enabled,
    }


@router.get("/rules", response_model=list[AlertRuleItem])
async def list_rules(db: AsyncSession = DbDep) -> list[dict]:
    """列出全部告警规则，按 id 升序（契约 §3.5）。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        list[dict]: 见 schemas.alert.AlertRuleItem。
    """
    result = await db.execute(select(AlertRule).order_by(AlertRule.id))
    return [_rule_dict(r) for r in result.scalars()]


@router.post("/rules")
async def create_rule(body: AlertRuleIn, db: AsyncSession = DbDep) -> dict:
    """创建告警规则。

    Args:
        body (AlertRuleIn): 规则字段与关联渠道 id 列表。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 新规则 id}``。
    """
    rule = AlertRule(**body.model_dump(exclude={"channel_ids"}), channels=body.channel_ids)
    db.add(rule)
    await db.flush()
    return {"id": rule.id}


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, body: AlertRuleIn, db: AsyncSession = DbDep) -> dict:
    """整体更新告警规则（全字段覆盖）。

    Args:
        rule_id (int): 规则 id。
        body (AlertRuleIn): 新的规则字段与关联渠道 id 列表。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 规则 id}``。

    Raises:
        NotFoundError: 规则不存在时。
    """
    rule = await db.get(AlertRule, rule_id)
    if not rule:
        raise NotFoundError(f"rule {rule_id} not found")
    for key, value in {**body.model_dump(exclude={"channel_ids"}), "channels": body.channel_ids}.items():
        setattr(rule, key, value)
    await db.flush()
    return {"id": rule.id}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = DbDep) -> dict:
    """删除告警规则，并先收尾其活跃事件。

    Args:
        rule_id (int): 规则 id。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 规则 id, "deleted": True}``。

    Raises:
        NotFoundError: 规则不存在时。
    """
    rule = await db.get(AlertRule, rule_id)
    if not rule:
        raise NotFoundError(f"rule {rule_id} not found")
    # 删除前收尾该规则的活跃事件：rule_id 失去主后 firing 永远无人 resolved
    await engine.resolve_rule_events(db, rule_id)
    await db.delete(rule)
    await db.flush()
    return {"id": rule_id, "deleted": True}


@router.get("/events", response_model=list[AlertEventItem])
async def list_events(
    limit: int = Query(default=50, ge=1, le=500),
    status: str = Query(default="all", pattern="^(firing|resolved|all)$"),
    db: AsyncSession = DbDep,
) -> list[dict]:
    """列出告警事件，按 id 倒序（契约 §3.5）。

    Args:
        limit (int): 返回条数上限，1-500，默认 50。
        status (str): 状态过滤，firing / resolved / all，默认 all。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        list[dict]: 见 schemas.alert.AlertEventItem。
    """
    query = select(AlertEvent).order_by(AlertEvent.id.desc()).limit(limit)
    if status != "all":
        query = query.where(AlertEvent.status == status)
    result = await db.execute(query)
    return [engine.event_dict(e) for e in result.scalars()]


@router.get("/channels", response_model=list[AlertChannelItem])
async def list_channels(db: AsyncSession = DbDep) -> list[dict]:
    """列出全部通知渠道，配置脱敏返回。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        list[dict]: 见 schemas.alert.AlertChannelItem（config_masked 为掩码后配置）。
    """
    result = await db.execute(select(AlertChannel).order_by(AlertChannel.id))
    return [
        {
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "enabled": c.enabled,
            "config_masked": mask_config(c.type, c.config),
        }
        for c in result.scalars()
    ]


def _channel_row(body: AlertChannelIn) -> AlertChannel:
    """按请求体构建渠道 ORM 行，配置先经渠道实现校验。

    Args:
        body (AlertChannelIn): 渠道字段与配置。

    Returns:
        AlertChannel: 尚未入库的渠道 ORM 对象。

    Raises:
        InvalidParamsError: 渠道类型合法但配置缺字段时（错误码 1002）。
    """
    impl = engine.channel_impl(body.type)
    impl.validate(body.config)  # 类型合法但缺字段 → 1002
    return AlertChannel(name=body.name, type=body.type, config=body.config, enabled=body.enabled)


@router.post("/channels")
async def create_channel(body: AlertChannelIn, db: AsyncSession = DbDep) -> dict:
    """创建通知渠道（配置先校验再入库）。

    Args:
        body (AlertChannelIn): 渠道字段与配置。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 新渠道 id}``。

    Raises:
        InvalidParamsError: 渠道类型合法但配置缺字段时。
    """
    channel = _channel_row(body)
    db.add(channel)
    await db.flush()
    return {"id": channel.id}


@router.put("/channels/{channel_id}")
async def update_channel(channel_id: int, body: AlertChannelIn, db: AsyncSession = DbDep) -> dict:
    """更新通知渠道（带掩码的字段合并回旧配置）。

    Args:
        channel_id (int): 渠道 id。
        body (AlertChannelIn): 新的渠道字段与配置。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 渠道 id}``。

    Raises:
        NotFoundError: 渠道不存在时。
        InvalidParamsError: 渠道类型合法但配置缺字段时。
    """
    channel = await db.get(AlertChannel, channel_id)
    if not channel:
        raise NotFoundError(f"channel {channel_id} not found")
    engine.channel_impl(body.type).validate(body.config)
    # 编辑表单回显的是 GET 脱敏值：仍带掩码（****）的字段合并回旧配置，
    # 避免把 "abcd****" 掩码串当成新凭据存库；其余字段（含新增键）按提交值更新
    merged = {
        key: channel.config.get(key)
        if isinstance(value, str) and "****" in value and key in channel.config
        else value
        for key, value in body.config.items()
    }
    channel.name, channel.type, channel.enabled = body.name, body.type, body.enabled
    channel.config = merged
    await db.flush()
    return {"id": channel.id}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: int, db: AsyncSession = DbDep) -> dict:
    """删除通知渠道。

    Args:
        channel_id (int): 渠道 id。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 渠道 id, "deleted": True}``。

    Raises:
        NotFoundError: 渠道不存在时。
    """
    channel = await db.get(AlertChannel, channel_id)
    if not channel:
        raise NotFoundError(f"channel {channel_id} not found")
    await db.delete(channel)
    await db.flush()
    return {"id": channel_id, "deleted": True}


@router.post("/channels/{channel_id}/test", response_model=ChannelTestResult)
async def test_channel(channel_id: int, db: AsyncSession = DbDep) -> dict:
    """向指定渠道发送测试通知，验证连通性。

    发送阶段除配置错误外的任何异常一律按失败计（success=False）。

    Args:
        channel_id (int): 渠道 id。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"channel_id": 渠道 id, "success": 是否发送成功}``。

    Raises:
        NotFoundError: 渠道不存在时。
        InvalidParamsError: 渠道类型未知或配置缺字段时（透传）。
    """
    channel = await db.get(AlertChannel, channel_id)
    if not channel:
        raise NotFoundError(f"channel {channel_id} not found")
    try:
        impl = engine.channel_impl(channel.type)
        ok = await impl.send(channel.config, "测试通知", "nasdeck 渠道连通性测试")
    except InvalidParamsError:
        raise
    except Exception:
        ok = False
    return {"channel_id": channel_id, "success": ok}
