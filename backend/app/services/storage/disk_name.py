"""磁盘自定义名称：按 serial 持久化（契约 §2.5 alias / §3.2 alias 接口）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.storage import DiskAlias


async def get_alias_map(db: AsyncSession) -> dict[str, str]:
    """读取全部磁盘自定义名称。

    Args:
        db (AsyncSession): 只读会话。

    Returns:
        dict[str, str]: serial → 自定义名称映射。
    """
    result = await db.execute(select(DiskAlias))
    return {row.serial: row.alias for row in result.scalars()}


async def set_alias(db: AsyncSession, serial: str, alias: str) -> str:
    """设置磁盘自定义名称（存在则更新，不存在则新建）。

    Args:
        db (AsyncSession): 调用方会话（本函数只 flush，commit 归调用方）。
        serial (str): 磁盘序列号（别名的持久化主键，契约 §2.5）。
        alias (str): 自定义名称。

    Returns:
        str: 生效后的别名（与入参 alias 相同）。
    """
    result = await db.execute(select(DiskAlias).where(DiskAlias.serial == serial))
    row = result.scalar_one_or_none()
    if row:
        row.alias = alias
    else:
        db.add(DiskAlias(serial=serial, alias=alias))
    await db.flush()
    return alias


async def delete_alias(db: AsyncSession, serial: str) -> None:
    """删除磁盘自定义名称。

    Args:
        db (AsyncSession): 调用方会话（本函数只 flush，commit 归调用方）。
        serial (str): 磁盘序列号。

    Raises:
        NotFoundError: 该序列号无别名记录（映射为接口 404）。
    """
    result = await db.execute(select(DiskAlias).where(DiskAlias.serial == serial))
    row = result.scalar_one_or_none()
    if not row:
        raise NotFoundError(f"alias not found for serial {serial}")
    await db.delete(row)
    await db.flush()
