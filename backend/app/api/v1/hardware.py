"""硬件清单只读接口（契约 §3.7：GET /hardware、GET /hardware/{kind}）。

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
    """取每个采集 kind 的最新一条记录。

    Args:
        db (AsyncSession): 数据库会话。

    Returns:
        dict[str, dict]: ``{kind: {name, available, ...props}}``。
    """
    latest_ids = select(HardwareItem.kind, func.max(HardwareItem.id).label("id")).group_by(HardwareItem.kind).subquery()
    result = await db.execute(
        select(HardwareItem).join(latest_ids, HardwareItem.id == latest_ids.c.id)
    )
    return {item.kind: {"name": item.name, **(item.props or {})} for item in result.scalars()}


@router.get("")
async def hardware_all(db: AsyncSession = DbDep) -> dict:
    """返回全部硬件清单（每类采集器最新一轮，契约 §3.7）。

    数据来自 slow_60s 每轮落库的 hardware_items。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{kind: {name, available, ...props}}``。
    """
    return await _latest_round(db)


@router.get("/{kind}")
async def hardware_one(kind: str, db: AsyncSession = DbDep) -> dict:
    """返回单类硬件清单（契约 §3.7）。

    Args:
        kind (str): 硬件类别（采集器 kind）。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"kind": kind, "name": ..., ...props}``。

    Raises:
        NotFoundError: 该 kind 无任何采集记录时。
    """
    items = await _latest_round(db)
    if kind not in items:
        raise NotFoundError(f"hardware kind not found: {kind}")
    return {"kind": kind, **items[kind]}
