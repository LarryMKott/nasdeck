"""容器资源 1m 桶（花活二期 M）：list_containers 一轮 → container_points 覆盖写。

挂在 slow_60s（1m 桶粒度即 60s 采样）；保留 7 天，翻日清理一次（smart_15m 同款
标记法）。只记 running 容器——退出容器的资源行没有意义，事件面由 docker_watch 负责。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import ContainerPoint
from app.services.system import docker as docker_service

KEEP_DAYS = 7

# 翻日清理标记（进程内；重启最多晚一个自然日清理，无害）
_last_day: str | None = None


def reset_for_test() -> None:
    """清空翻日标记（测试隔离）。"""
    global _last_day
    _last_day = None


async def record_tick(db: AsyncSession, now: datetime | None = None) -> int:
    """采样一轮 running 容器 → 本分整桶覆盖写，返回写入行数。

    Args:
        db (AsyncSession): 调用方会话（只 flush，commit 归调用方）。
        now (datetime | None): 桶键基准；None 取当前 UTC。

    Returns:
        int: 写入行数；docker 不可用 / 无 running 容器时 0。
    """
    global _last_day
    now = now or datetime.now(UTC)
    key = now.strftime("%Y-%m-%dT%H:%M:00")
    result = await docker_service.list_containers()
    if not result.get("available"):
        return 0
    rows = [
        ContainerPoint(
            ts=key,
            name=c["name"][:64],
            cpu_percent=c.get("cpu_percent"),
            mem_mb=round(c["mem_bytes"] / 1024**2, 1) if c.get("mem_bytes") is not None else None,
            read_kbps=round(c["read_bps"] / 1024, 1) if c.get("read_bps") is not None else None,
            write_kbps=round(c["write_bps"] / 1024, 1) if c.get("write_bps") is not None else None,
        )
        for c in result["containers"]
        if c.get("state") == "running"
    ]
    if not rows:
        return 0
    names = {r.name for r in rows}
    await db.execute(
        delete(ContainerPoint).where(ContainerPoint.ts == key, ContainerPoint.name.in_(names))
    )
    db.add_all(rows)

    # 翻日清理：每日一次（同 smart_15m 标记法）
    today = now.strftime("%Y-%m-%d")
    if _last_day != today:
        await prune_old(db, now=now)
        _last_day = today
    await db.flush()
    return len(rows)


async def prune_old(db: AsyncSession, now: datetime | None = None) -> int:
    """删除超保留窗（7 天）的容器点，返回删除行数。"""
    cutoff = ((now or datetime.now(UTC)) - timedelta(days=KEEP_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    result = await db.execute(delete(ContainerPoint).where(ContainerPoint.ts < cutoff))
    return result.rowcount or 0


async def trend(db: AsyncSession, name: str, hours: int = 24) -> dict:
    """单容器资源趋势（1m 桶，最长 7 天窗口）。

    Args:
        db (AsyncSession): 只读会话。
        name (str): 容器名。
        hours (int): 回看小时数（1–168）。

    Returns:
        dict: {name, hours, points}，points 按 ts 升序，每点
            {ts, cpu_percent, mem_mb, read_kbps, write_kbps}；无记录为空数组。
    """
    since = ((datetime.now(UTC)) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    result = await db.execute(
        select(
            ContainerPoint.ts,
            ContainerPoint.cpu_percent,
            ContainerPoint.mem_mb,
            ContainerPoint.read_kbps,
            ContainerPoint.write_kbps,
        )
        .where(ContainerPoint.name == name, ContainerPoint.ts >= since)
        .order_by(ContainerPoint.ts)
    )
    points = [
        {
            "ts": r[0],
            "cpu_percent": r[1],
            "mem_mb": r[2],
            "read_kbps": r[3],
            "write_kbps": r[4],
        }
        for r in result.all()
    ]
    return {"name": name, "hours": hours, "points": points}
