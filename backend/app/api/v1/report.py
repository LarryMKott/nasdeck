"""报告接口（契约 §3.6：生成/列表/下载，文件流非信封）。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import ApiKeyDep
from app.services.report import diagnostic, html_generator
from app.utils.validators import validate_report_filename

router = APIRouter(prefix="/report", tags=["report"], dependencies=[ApiKeyDep])


@router.post("/health")
async def generate_health(redact: bool = Query(default=True)) -> dict:
    from app.services.monitor import temperature
    from app.services.monitor.cache import realtime_cache
    from app.services.storage import volumes as volume_service

    snap = realtime_cache.get("realtime") or {}
    temps = realtime_cache.get("temperatures") or await temperature.temperatures()
    disks = await volume_service.list_disks()
    payload = {
        "kv": {
            "CPU": f"{snap.get('cpu_percent', 0)}%",
            "内存": f"{snap.get('mem_percent', 0)}%",
            "最高温度": temperature.max_celsius(temps) or "—",
            "运行时长": f"{snap.get('uptime_s', 0)} s",
        },
        "disks": disks,
    }
    return await html_generator.generate_health_report(payload, redact)


@router.get("/health/list")
async def list_reports() -> dict:
    files = sorted(
        (f.name for f in html_generator.REPORT_DIR.glob("health_*.html")),
        reverse=True,
    )
    return {"files": files}


@router.get("/health/{filename}", response_class=FileResponse)
async def download_health(filename: str) -> Path:
    name = validate_report_filename(filename)
    path = html_generator.REPORT_DIR / name
    if not path.exists():
        from app.core.exceptions import NotFoundError

        raise NotFoundError(f"report not found: {name}")
    return path


@router.post("/diagnostic")
async def generate_diagnostic(redact: bool = Query(default=True)) -> dict:
    return await diagnostic.generate_diagnostic(redact)


@router.get("/diagnostic/{filename}", response_class=FileResponse)
async def download_diagnostic(filename: str) -> Path:
    name = validate_report_filename(filename)
    path = diagnostic.REPORT_DIR / name
    if not path.exists():
        from app.core.exceptions import NotFoundError

        raise NotFoundError(f"diagnostic not found: {name}")
    return path
