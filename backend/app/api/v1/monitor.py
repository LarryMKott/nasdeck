"""监控接口（契约 §3.1）。realtime 缓存 TTL 5s 优先，缺失即采。"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiKeyDep, DbDep, TrimAuthDep
from app.schemas.monitor import CheckupResponse, HistoryResponse, RealtimeSnapshot, Summary, TemperatureItem
from app.services.monitor import checkup as checkup_service
from app.services.monitor import history as history_service
from app.services.monitor import system_resources, temperature
from app.services.monitor.cache import realtime_cache
from app.services.storage import volumes as volume_service

router = APIRouter(prefix="/monitor", tags=["monitor"], dependencies=[ApiKeyDep, TrimAuthDep])


@router.get("/checkup", response_model=CheckupResponse)
async def checkup(db: AsyncSession = DbDep) -> dict:
    """一键体检（花活二期 N）：六维聚合只读端点，零新增采集。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.monitor.CheckupResponse。
    """
    return await checkup_service.run_checkup(db)


@router.get("/realtime", response_model=RealtimeSnapshot)
async def realtime() -> dict:
    """实时监控快照（CPU/内存/负载/GPU 等，契约 §3.1）。

    realtime 缓存 TTL 5s 优先，缺失即采。

    Returns:
        dict: 见 schemas.monitor.RealtimeSnapshot。
    """
    snap = realtime_cache.get("realtime")
    if snap is None:
        snap = await system_resources.snapshot()
        snap["gpu"] = realtime_cache.get("gpu")  # GPU 由 medium_5s 采样维护
        realtime_cache.set("realtime", snap, ttl=5)
    return snap


@router.get("/temperatures", response_model=list[TemperatureItem])
async def temperatures() -> list[dict]:
    """全部温度传感器读数（缓存 TTL 15s）。

    Returns:
        list[dict]: 见 schemas.monitor.TemperatureItem。
    """
    items = realtime_cache.get("temperatures")
    if items is None:
        items = await temperature.temperatures()
        realtime_cache.set("temperatures", items, ttl=15)
    return items


@router.get("/history", response_model=HistoryResponse)
async def history_api(
    db: AsyncSession = DbDep,
    minutes: int = Query(default=60, ge=1, le=43200),
    points: int = Query(default=200, ge=10, le=500),
) -> dict:
    """历史监控曲线查询（契约 §3.1）。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。
        minutes (int): 回溯窗口分钟数，1-43200，默认 60。
        points (int): 降采样点数，10-500，默认 200。

    Returns:
        dict: ``{"points": 采样点列表, "minutes": 窗口, "granularity": 桶粒度}``。
    """
    rows, granularity = await history_service.query_history(db, minutes, points)
    return {"points": rows, "minutes": minutes, "granularity": granularity}


@router.get("/summary", response_model=Summary)
async def summary(db: AsyncSession = DbDep) -> dict:
    """监控总览（CPU/内存/最高温/运行时长/磁盘健康计数等，契约 §3.1）。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.monitor.Summary。
    """
    snap = realtime_cache.get("realtime")
    if snap is None:
        snap = await system_resources.snapshot()
        realtime_cache.set("realtime", snap, ttl=5)
    temps = realtime_cache.get("temperatures")
    if temps is None:
        temps = await temperature.temperatures()
        realtime_cache.set("temperatures", temps, ttl=15)  # 回写与 realtime/temperatures 分支对齐，并发请求不重复扫描
    disks = await volume_service.list_disks()
    # 磁盘健康来自 SMART 扫描缓存（slow_tick 维护）；缓存未热时按 unknown 计，
    # 不回退 unknown 之外的猜测值
    health_map = realtime_cache.get("disk_health") or {}
    counts = {"passed": 0, "warning": 0, "failing": 0, "unknown": 0}
    for disk in disks:
        counts[health_map.get(disk.get("device"), "unknown")] = (
            counts.get(health_map.get(disk.get("device"), "unknown"), 0) + 1
        )
    return {
        "cpu_percent": snap["cpu_percent"],
        "mem_percent": snap["mem_percent"],
        "temp_max_c": temperature.max_celsius(temps),
        "uptime_s": snap["uptime_s"],
        "disk_total": len(disks),
        "disk_health": counts,
        "raid_degraded": realtime_cache.get("raid_degraded") or 0,
    }

@router.get("/history/stats")
async def history_stats(
    db: AsyncSession = DbDep,
    minutes: int = Query(default=60, ge=1, le=43200),
    dim: str = Query(default="cpu", pattern="^(cpu|mem|temp|net|disk|gpu)$"),
) -> dict:
    """区间统计（契约 §3.1）。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。
        minutes (int): 回溯窗口分钟数，1-43200，默认 60。
        dim (str): 统计维度，cpu/mem/temp/net/disk/gpu 之一。

    Returns:
        dict: 该维度在窗口内的统计结果。
    """
    return await history_service.stats(db, minutes, dim)


@router.get("/history/export")
async def history_export(
    db: AsyncSession = DbDep,
    minutes: int = Query(default=60, ge=1, le=43200),
    dim: str = Query(default="cpu", pattern="^(cpu|mem|temp|net|disk|gpu)$"),
    fmt: str = Query(default="csv", pattern="^(csv|markdown|html)$"),
) -> Response:
    """历史健康报告导出（契约 §3.1：文件流，非信封）。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。
        minutes (int): 回溯窗口分钟数，1-43200，默认 60。
        dim (str): 导出维度，cpu/mem/temp/net/disk/gpu 之一。
        fmt (str): 导出格式，csv/markdown/html 之一，默认 csv。

    Returns:
        Response: 带附件头的文件流响应（charset=utf-8）。
    """
    rows, _granularity = await history_service.query_history(db, minutes, 500)
    filename, content, media_type = history_service.export_build(rows, dim, minutes, fmt)
    return Response(
        content,
        media_type=f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
