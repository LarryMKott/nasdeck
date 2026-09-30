"""系统接口（契约 §3.3）。"""

from __future__ import annotations

import platform
from datetime import UTC, datetime

import psutil
from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiKeyDep, DbDep, TrimAuthDep
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.system import KillWhitelist, SystemSetting
from app.schemas.system import (
    DockerResponse,
    PortAliasIn,
    PortAliasOut,
    PortEntry,
    ProcessItem,
    SettingPut,
    SystemInfo,
    WhitelistIn,
    WhitelistItem,
)
from app.services.system import docker as docker_service
from app.services.system import ports as port_service
from app.services.system import process as process_service
from app.utils.sysfs import read_text

router = APIRouter(prefix="/system", tags=["system"], dependencies=[ApiKeyDep, TrimAuthDep])


@router.get("/info", response_model=SystemInfo)
async def info() -> dict:
    return {
        "hostname": platform.node(),
        "platform": platform.system(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "os_release": read_text("/etc/os-release") or platform.platform(),
        "fnos_version": read_text("/usr/trim/etc/version"),
        "uptime_s": int(datetime.now(UTC).timestamp() - psutil.boot_time()),
        "app_version": settings.app_version,
    }


@router.get("/env")
async def env_check() -> dict:
    """运行环境自检（安装期自举结果的实时呈现，契约 §2.14 EnvCheck）。

    实时探测而非读安装报告：工具后来补装、驱动状态变化都能如实反映；
    缺失项带安装提示（对应 install_callback「缺啥装啥、失败降级」的兜底说明）。
    """
    import shutil
    import sys
    from pathlib import Path

    def tool(name: str, desc: str, pkg: str) -> dict:
        found = shutil.which(name)
        return {
            "name": name,
            "desc": desc,
            "ok": bool(found),
            "path": found or "",
            "install": "" if found else pkg,
        }

    resolved_storcli = settings.storcli_cmd
    storcli_ok = bool(shutil.which(resolved_storcli)) or Path(resolved_storcli).exists()
    return {
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "config": {
            "port": settings.port,
            "host": settings.host,
            "log_level": settings.resolved_log_level,
            "raw_keep_minutes": settings.raw_keep_minutes,
            "trim_auth": settings.trim_auth,
        },
        "tools": [
            tool("smartctl", "硬盘 SMART 读取", "smartmontools"),
            tool("sensors", "温度/风扇/电压传感", "lm-sensors"),
            tool("mdadm", "软 RAID 阵列状态", "mdadm"),
            tool("dmidecode", "主板/内存条信息", "dmidecode"),
            tool("decode-dimms", "内存温度", "i2c-tools"),
            tool("ethtool", "网卡信息与 WOL", "ethtool"),
        ],
        "drivers": [
            {"name": "nct6775", "desc": "风扇芯片驱动（Nuvoton 新机型）", "loaded": Path("/sys/module/nct6775").is_dir()},
            {"name": "it87", "desc": "风扇芯片驱动（ITE 旧机型）", "loaded": Path("/sys/module/it87").is_dir()},
        ],
        "storcli": {
            "ok": storcli_ok,
            "path": resolved_storcli if storcli_ok else "",
            "desc": "LSI MegaRAID/HBA 阵列卡工具",
        },
    }


@router.get("/docker/containers", response_model=DockerResponse)
async def docker_containers(stats: bool = Query(default=False)) -> dict:
    # stats=true 的逐容器资源占用较慢；当前版本透传标记，资源字段为可选（契约 §2.11）
    return await docker_service.list_containers(with_stats=stats)


@router.get("/ports", response_model=list[PortEntry])
async def get_ports(db: AsyncSession = DbDep) -> list[dict]:
    return await port_service.list_ports(db)


@router.post("/ports/alias", response_model=PortAliasOut)
async def post_port_alias(body: PortAliasIn, db: AsyncSession = DbDep) -> dict:
    row = await port_service.upsert_alias(db, body.port, body.label, body.note)
    return {"id": row.id, "port": row.port, "label": row.label, "note": row.note}


@router.get("/processes", response_model=list[ProcessItem])
async def get_processes(
    sort: str = Query(default="cpu", pattern="^(cpu|mem)$"),
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = DbDep,
) -> list[dict]:
    return await process_service.list_processes(db, sort, limit)


@router.delete("/processes/{pid}")
async def kill_process(pid: int, confirm: bool = Query(default=False), db: AsyncSession = DbDep) -> dict:
    return await process_service.kill_process(db, pid, confirm)


@router.get("/whitelist", response_model=list[WhitelistItem])
async def get_whitelist(db: AsyncSession = DbDep) -> list[dict]:
    result = await db.execute(select(KillWhitelist).order_by(KillWhitelist.name))
    return [{"id": w.id, "name": w.name, "reason": w.reason} for w in result.scalars()]


@router.post("/whitelist", response_model=WhitelistItem)
async def post_whitelist(body: WhitelistIn, db: AsyncSession = DbDep) -> dict:
    result = await db.execute(select(KillWhitelist).where(KillWhitelist.name == body.name))
    row = result.scalar_one_or_none()
    if row:
        row.reason = body.reason
    else:
        row = KillWhitelist(name=body.name, reason=body.reason)
        db.add(row)
    await db.flush()
    return {"id": row.id, "name": row.name, "reason": row.reason}


@router.delete("/whitelist/{item_id}")
async def delete_whitelist(item_id: int, db: AsyncSession = DbDep) -> dict:
    row = await db.get(KillWhitelist, item_id)
    if not row:
        raise NotFoundError(f"whitelist item {item_id} not found")
    await db.delete(row)
    await db.flush()
    return {"id": item_id, "deleted": True}


@router.get("/settings")
async def get_settings(db: AsyncSession = DbDep) -> dict:
    result = await db.execute(select(SystemSetting))
    return {row.key: {"value": row.value, "description": row.description} for row in result.scalars()}


@router.put("/settings/{key}")
async def put_setting(key: str, body: SettingPut, db: AsyncSession = DbDep) -> dict:
    row = await db.get(SystemSetting, key)
    if row:
        row.value, row.description = body.value, body.description or row.description
    else:
        row = SystemSetting(key=key, value=body.value, description=body.description)
        db.add(row)
    await db.flush()
    return {"key": key, "value": body.value}
