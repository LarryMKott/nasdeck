"""监控接口（契约 §3.1）。realtime 缓存 TTL 5s 优先，缺失即采。"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiKeyDep, DbDep, TrimAuthDep
from app.schemas.monitor import HistoryResponse, RealtimeSnapshot, Summary, TemperatureItem
from app.services.monitor import history as history_service
from app.services.monitor import system_resources, temperature
from app.services.monitor.cache import realtime_cache
from app.services.storage import volumes as volume_service

router = APIRouter(prefix="/monitor", tags=["monitor"], dependencies=[ApiKeyDep, TrimAuthDep])


@router.get("/realtime", response_model=RealtimeSnapshot)
async def realtime() -> dict:
    snap = realtime_cache.get("realtime")
    if snap is None:
        snap = await system_resources.snapshot()
        realtime_cache.set("realtime", snap, ttl=5)
    return snap


@router.get("/temperatures", response_model=list[TemperatureItem])
async def temperatures() -> list[dict]:
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
    rows, granularity = await history_service.query_history(db, minutes, points)
    return {"points": rows, "minutes": minutes, "granularity": granularity}


@router.get("/summary", response_model=Summary)
async def summary(db: AsyncSession = DbDep) -> dict:
    snap = realtime_cache.get("realtime")
    if snap is None:
        snap = await system_resources.snapshot()
        realtime_cache.set("realtime", snap, ttl=5)
    temps = realtime_cache.get("temperatures")
    if temps is None:
        temps = await temperature.temperatures()
    disks = await volume_service.list_disks()
    counts = {"passed": 0, "warning": 0, "failing": 0, "unknown": 0}
    for disk in disks:
        counts[disk.get("health", "unknown")] = counts.get(disk.get("health", "unknown"), 0) + 1
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
    """区间统计（契约 §3.1）。"""
    return await history_service.stats(db, minutes, dim)


@router.get("/history/export")
async def history_export(
    db: AsyncSession = DbDep,
    minutes: int = Query(default=60, ge=1, le=43200),
    dim: str = Query(default="cpu", pattern="^(cpu|mem|temp|net|disk|gpu)$"),
    fmt: str = Query(default="csv", pattern="^(csv|markdown|html)$"),
) -> Response:
    """历史健康报告导出（契约 §3.1：文件流，非信封）。"""
    rows, _granularity = await history_service.query_history(db, minutes, 500)
    filename, content, media_type = history_service.export_build(rows, dim, minutes, fmt)
    return Response(
        content,
        media_type=f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
