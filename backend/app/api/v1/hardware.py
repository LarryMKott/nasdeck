"""硬件清单只读接口（契约 §6.3 规划：GET /hardware、GET /hardware/{kind}）。

数据来自 slow_60s 每轮落库的 hardware_items；返回每类采集器的最新一轮。
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiKeyDep, DbDep, TrimAuthDep
from app.core.exceptions import NotFoundError
from app.models.hardware import HardwareItem

router = APIRouter(prefix="/hardware", tags=["hardware"], dependencies=[ApiKeyDep, TrimAuthDep])


async def _latest_round(db: AsyncSession) -> dict[str, dict]:
    """每个 kind 的最新一条 → {kind: {name, available, ...props}}。"""
    latest_ids = select(HardwareItem.kind, func.max(HardwareItem.id).label("id")).group_by(HardwareItem.kind).subquery()
    result = await db.execute(
        select(HardwareItem).join(latest_ids, HardwareItem.id == latest_ids.c.id)
    )
    return {item.kind: {"name": item.name, **(item.props or {})} for item in result.scalars()}


@router.get("")
async def hardware_all(db: AsyncSession = DbDep) -> dict:
    return await _latest_round(db)


@router.get("/{kind}")
async def hardware_one(kind: str, db: AsyncSession = DbDep) -> dict:
    items = await _latest_round(db)
    if kind not in items:
        raise NotFoundError(f"hardware kind not found: {kind}")
    return {"kind": kind, **items[kind]}
