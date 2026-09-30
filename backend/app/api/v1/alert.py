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
    return {
        "id": rule.id,
        "name": rule.name,
        "metric": rule.metric,
        "comparator": rule.comparator,
        "threshold": rule.threshold,
        "duration_ticks": rule.duration_ticks,
        "severity": rule.severity,
        "channel_ids": rule.channels,
        "enabled": rule.enabled,
    }


@router.get("/rules", response_model=list[AlertRuleItem])
async def list_rules(db: AsyncSession = DbDep) -> list[dict]:
    result = await db.execute(select(AlertRule).order_by(AlertRule.id))
    return [_rule_dict(r) for r in result.scalars()]


@router.post("/rules")
async def create_rule(body: AlertRuleIn, db: AsyncSession = DbDep) -> dict:
    rule = AlertRule(**body.model_dump(exclude={"channel_ids"}), channels=body.channel_ids)
    db.add(rule)
    await db.flush()
    return {"id": rule.id}


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, body: AlertRuleIn, db: AsyncSession = DbDep) -> dict:
    rule = await db.get(AlertRule, rule_id)
    if not rule:
        raise NotFoundError(f"rule {rule_id} not found")
    for key, value in {**body.model_dump(exclude={"channel_ids"}), "channels": body.channel_ids}.items():
        setattr(rule, key, value)
    await db.flush()
    return {"id": rule.id}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = DbDep) -> dict:
    rule = await db.get(AlertRule, rule_id)
    if not rule:
        raise NotFoundError(f"rule {rule_id} not found")
    await db.delete(rule)
    await db.flush()
    return {"id": rule_id, "deleted": True}


@router.get("/events", response_model=list[AlertEventItem])
async def list_events(
    limit: int = Query(default=50, ge=1, le=500),
    status: str = Query(default="all", pattern="^(firing|resolved|all)$"),
    db: AsyncSession = DbDep,
) -> list[dict]:
    query = select(AlertEvent).order_by(AlertEvent.id.desc()).limit(limit)
    if status != "all":
        query = query.where(AlertEvent.status == status)
    result = await db.execute(query)
    return [engine._event_dict(e) for e in result.scalars()]


@router.get("/channels", response_model=list[AlertChannelItem])
async def list_channels(db: AsyncSession = DbDep) -> list[dict]:
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
    impl = engine.channel_impl(body.type)
    impl.validate(body.config)  # 类型合法但缺字段 → 1002
    return AlertChannel(name=body.name, type=body.type, config=body.config, enabled=body.enabled)


@router.post("/channels")
async def create_channel(body: AlertChannelIn, db: AsyncSession = DbDep) -> dict:
    channel = _channel_row(body)
    db.add(channel)
    await db.flush()
    return {"id": channel.id}


@router.put("/channels/{channel_id}")
async def update_channel(channel_id: int, body: AlertChannelIn, db: AsyncSession = DbDep) -> dict:
    channel = await db.get(AlertChannel, channel_id)
    if not channel:
        raise NotFoundError(f"channel {channel_id} not found")
    engine.channel_impl(body.type).validate(body.config)
    channel.name, channel.type, channel.config, channel.enabled = body.name, body.type, body.config, body.enabled
    await db.flush()
    return {"id": channel.id}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: int, db: AsyncSession = DbDep) -> dict:
    channel = await db.get(AlertChannel, channel_id)
    if not channel:
        raise NotFoundError(f"channel {channel_id} not found")
    await db.delete(channel)
    await db.flush()
    return {"id": channel_id, "deleted": True}


@router.post("/channels/{channel_id}/test", response_model=ChannelTestResult)
async def test_channel(channel_id: int, db: AsyncSession = DbDep) -> dict:
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
