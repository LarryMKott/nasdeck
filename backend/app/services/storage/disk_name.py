"""磁盘自定义名称：按 serial 持久化（契约 §2.5 alias / §3.2 alias 接口）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.storage import DiskAlias


async def get_alias_map(db: AsyncSession) -> dict[str, str]:
    result = await db.execute(select(DiskAlias))
    return {row.serial: row.alias for row in result.scalars()}


async def set_alias(db: AsyncSession, serial: str, alias: str) -> str:
    result = await db.execute(select(DiskAlias).where(DiskAlias.serial == serial))
    row = result.scalar_one_or_none()
    if row:
        row.alias = alias
    else:
        db.add(DiskAlias(serial=serial, alias=alias))
    await db.flush()
    return alias


async def delete_alias(db: AsyncSession, serial: str) -> None:
    result = await db.execute(select(DiskAlias).where(DiskAlias.serial == serial))
    row = result.scalar_one_or_none()
    if not row:
        raise NotFoundError(f"alias not found for serial {serial}")
    await db.delete(row)
    await db.flush()
