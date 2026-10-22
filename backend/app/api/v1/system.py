"""系统接口（契约 §3.3）。"""

from __future__ import annotations

import platform
from datetime import UTC, datetime

import psutil
from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiKeyDep, DbDep, TrimAuthDep
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.system import KillWhitelist, SystemSetting
from app.schemas.system import (
    ConfigExportIn,
    ContainerTrendResponse,
    DockerResponse,
    NetworkMap,
    PortAliasIn,
    PortAliasOut,
    PortEntry,
    ProcessItem,
    ReportScheduleIn,
    ReportScheduleOut,
    SelftestScheduleIn,
    SelftestScheduleOut,
    SettingPut,
    SystemInfo,
    WhitelistIn,
    WhitelistItem,
)
from app.services.hardware.policy import TOOLS, get_policy
from app.services.report import digest as report_digest
from app.services.storage import selftest_schedule
from app.services.system import backup as backup_service
from app.services.system import container_points as container_points_service
from app.services.system import docker as docker_service
from app.services.system import ports as port_service
from app.services.system import process as process_service
from app.utils.sysfs import read_text

router = APIRouter(prefix="/system", tags=["system"], dependencies=[ApiKeyDep, TrimAuthDep])


@router.get("/info", response_model=SystemInfo)
async def info(request: Request) -> dict:
    """系统基础信息（主机名/内核/发行版/fnOS 版本/运行时长等，契约 §3.3）。

    Args:
        request (Request): FastAPI 请求对象（框架注入，用于读取 trim 管理员头）。

    Returns:
        dict: 见 schemas.system.SystemInfo。
    """
    # 权限铁律的前端依据：trim 形态按飞牛注入的 X-Trim-Isadmin 头；
    # 非 trim 形态（api_key/本机无鉴权）恒 true——写权限归 api_key 持有者
    if settings.trim_auth:
        is_admin = request.headers.get("x-trim-isadmin", "").strip().lower() in ("true", "1")
    else:
        is_admin = True
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
        "is_admin": is_admin,
    }


@router.get("/env")
async def env_check() -> dict:
    """运行环境自检（安装期自举结果的实时呈现，契约 §2.14 EnvCheck）。

    实时探测而非读安装报告：工具后来补装、驱动状态变化都能如实反映；
    缺失项带安装提示（对应 install_callback「缺啥装啥、失败降级」的兜底说明）。
    工具清单与用途说明来自策略决策层 TOOLS 注册表（单一来源）。

    Returns:
        dict: 含 schemes/python/config/tools/drivers/storcli 各节的自检结果。
    """
    import shutil
    import sys
    from pathlib import Path

    def tool(name: str) -> dict:
        """组装单个外部工具的探测结果条目。"""
        found = shutil.which(name)
        desc, pkg = TOOLS[name]
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
        # 逐域采集方案（策略决策层启动时判定：本机实际采用的数据源/回退/降级原因）
        "schemes": get_policy().schemes,
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "config": {
            "port": settings.port,
            "host": settings.host,
            "log_level": settings.resolved_log_level,
            "raw_keep_minutes": settings.raw_keep_minutes,
            "trim_auth": settings.trim_auth,
        },
        "tools": [tool(name) for name in TOOLS],
        "drivers": [
            {
                "name": "nct6775",
                "desc": "风扇芯片驱动（Nuvoton 新机型）",
                "loaded": Path("/sys/module/nct6775").is_dir(),
            },
            {"name": "it87", "desc": "风扇芯片驱动（ITE 旧机型）", "loaded": Path("/sys/module/it87").is_dir()},
        ],
        "storcli": {
            "ok": storcli_ok,
            "path": resolved_storcli if storcli_ok else "",
            "desc": "LSI MegaRAID/HBA 阵列卡工具",
        },
    }


@router.get("/docker/containers", response_model=DockerResponse)
async def docker_containers() -> dict:
    """列出 Docker 容器状态。

    Returns:
        dict: 见 schemas.system.DockerResponse。
    """
    return await docker_service.list_containers()


@router.get("/docker/containers/{name}/trend", response_model=ContainerTrendResponse)
async def docker_container_trend(
    name: str,
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = DbDep,
) -> dict:
    """单容器资源趋势（1m 桶，最长 7 天；花活二期 M）。

    Args:
        name (str): 容器名。
        hours (int): 回看小时数（1-168）。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.system.ContainerTrendResponse。
    """
    return await container_points_service.trend(db, name, hours)


@router.post("/docker/containers/{name}/{action}")
async def docker_container_control(name: str, action: str) -> dict:
    """容器生命周期控制：start/stop/restart（花活二期 M）。

    写操作经路由级 TrimAuthDep 非 GET 管理员强校验；演示/无 docker CLI 时 500
    信封（ExternalToolError）。

    Args:
        name (str): 容器名（docker 命名约束校验，防注入）。
        action (str): start / stop / restart。

    Returns:
        dict: {name, action, ok: True}。
    """
    return await docker_service.container_control(name, action)


@router.get("/network/map", response_model=NetworkMap)
async def network_map() -> dict:
    """网络星图数据面（花活二期 L）：LISTEN/ESTABLISHED 聚合 + 远端内网外网归类。

    Returns:
        dict: 见 schemas.system.NetworkMap。
    """
    return port_service.network_map()


@router.get("/ports", response_model=list[PortEntry])
async def get_ports(db: AsyncSession = DbDep) -> list[dict]:
    """列出监听端口及用户标注的别名。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        list[dict]: 见 schemas.system.PortEntry。
    """
    return await port_service.list_ports(db)


@router.post("/ports/alias", response_model=PortAliasOut)
async def post_port_alias(body: PortAliasIn, db: AsyncSession = DbDep) -> dict:
    """新增/更新端口别名标注（按端口号 upsert）。

    Args:
        body (PortAliasIn): 端口号、标签与备注。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.system.PortAliasOut。
    """
    row = await port_service.upsert_alias(db, body.port, body.label, body.note)
    return {"id": row.id, "port": row.port, "label": row.label, "note": row.note}


@router.get("/processes", response_model=list[ProcessItem])
async def get_processes(
    sort: str = Query(default="cpu", pattern="^(cpu|mem)$"),
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = DbDep,
) -> list[dict]:
    """列出资源占用最高的进程。

    Args:
        sort (str): 排序依据，cpu 或 mem，默认 cpu。
        limit (int): 返回条数上限，1-500，默认 50。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        list[dict]: 见 schemas.system.ProcessItem。
    """
    return await process_service.list_processes(db, sort, limit)


@router.delete("/processes/{pid}")
async def kill_process(pid: int, confirm: bool = Query(default=False), db: AsyncSession = DbDep) -> dict:
    """终止指定进程（白名单内进程受保护）。

    Args:
        pid (int): 进程 id。
        confirm (bool): 二次确认开关，必须为 true 才执行终止。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"pid": 进程 id, "name": 进程名, "killed": True}``。

    Raises:
        PermissionDeniedError: confirm 未开或进程在保护名单内时。
        NotFoundError: 进程不存在时。
    """
    return await process_service.kill_process(db, pid, confirm)


@router.get("/whitelist", response_model=list[WhitelistItem])
async def get_whitelist(db: AsyncSession = DbDep) -> list[dict]:
    """列出进程终止保护白名单。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        list[dict]: 见 schemas.system.WhitelistItem。
    """
    result = await db.execute(select(KillWhitelist).order_by(KillWhitelist.name))
    return [{"id": w.id, "name": w.name, "reason": w.reason} for w in result.scalars()]


@router.post("/whitelist", response_model=WhitelistItem)
async def post_whitelist(body: WhitelistIn, db: AsyncSession = DbDep) -> dict:
    """新增或更新白名单条目（按进程名 upsert）。

    Args:
        body (WhitelistIn): 进程名与保护原因。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.system.WhitelistItem。
    """
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
    """删除白名单条目。

    Args:
        item_id (int): 白名单条目 id。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 条目 id, "deleted": True}``。

    Raises:
        NotFoundError: 条目不存在时。
    """
    row = await db.get(KillWhitelist, item_id)
    if not row:
        raise NotFoundError(f"whitelist item {item_id} not found")
    await db.delete(row)
    await db.flush()
    return {"id": item_id, "deleted": True}


@router.get("/settings")
async def get_settings(db: AsyncSession = DbDep) -> dict:
    """列出全部系统设置项（键值与说明）。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{key: {"value": 值, "description": 说明}}``。
    """
    result = await db.execute(select(SystemSetting))
    return {row.key: {"value": row.value, "description": row.description} for row in result.scalars()}


@router.put("/settings/{key}")
async def put_setting(key: str, body: SettingPut, db: AsyncSession = DbDep) -> dict:
    """写入单个系统设置项（键不存在则创建）。

    Args:
        key (str): 设置键。
        body (SettingPut): 新值与描述。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"key": 键, "value": 新值}``。
    """
    row = await db.get(SystemSetting, key)
    if row:
        row.value, row.description = body.value, body.description or row.description
    else:
        row = SystemSetting(key=key, value=body.value, description=body.description)
        db.add(row)
    await db.flush()
    return {"key": key, "value": body.value}


@router.get("/selftest-schedule", response_model=SelftestScheduleOut)
async def get_selftest_schedule(db: AsyncSession = DbDep) -> dict:
    """查询 SMART 巡检计划及最近一次执行日期。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.system.SelftestScheduleOut（含 last_run）。
    """
    cfg = await selftest_schedule.load_schedule(db)
    cfg["last_run"] = await selftest_schedule.last_run_date(db) or None
    return cfg


@router.put("/selftest-schedule", response_model=SelftestScheduleOut)
async def put_selftest_schedule(body: SelftestScheduleIn, db: AsyncSession = DbDep) -> dict:
    """保存 SMART 巡检计划。

    写操作仅管理员，由路由级 TrimAuthDep 强校验。last_run 只读。

    Args:
        body (SelftestScheduleIn): 计划开关、星期、小时与自检类型。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.system.SelftestScheduleOut（含 last_run）。
    """
    cfg = await selftest_schedule.save_schedule(
        db, {"enabled": body.enabled, "weekday": body.weekday, "hour": body.hour, "type": body.type}
    )
    cfg["last_run"] = await selftest_schedule.last_run_date(db) or None
    return cfg


@router.post("/config-export")
async def export_config(body: ConfigExportIn, db: AsyncSession = DbDep) -> dict:
    """导出用户配置备份（POST 动词语义：trim 路由级鉴权对非 GET 强校验管理员）。

    Args:
        body (ConfigExportIn): include_secrets=True 时渠道凭据明文导出。
        db (AsyncSession): 请求级会话。

    Returns:
        dict: 备份 JSON（schema_version 锚定导入兼容性）。
    """
    return await backup_service.export_config(db, include_secrets=body.include_secrets)


@router.post("/config-import")
async def import_config(body: dict, db: AsyncSession = DbDep) -> dict:
    """导入配置备份（replace-all 单事务；schema_version 不匹配整体拒绝 1002）。

    Args:
        body (dict): config-export 输出的备份 JSON。
        db (AsyncSession): 请求级会话（get_db 统一 commit / 异常回滚）。

    Returns:
        dict: 各表导入计数。
    """
    return await backup_service.import_config(db, body)


@router.get("/report-schedule", response_model=ReportScheduleOut)
async def get_report_schedule(db: AsyncSession = DbDep) -> dict:
    """周报推送计划（selftest-schedule 同款形态；weekday 0=周一）。"""
    cfg = await report_digest.load_schedule(db)
    cfg["last_run"] = await report_digest.last_run_date(db) or None
    return cfg


@router.put("/report-schedule", response_model=ReportScheduleOut)
async def put_report_schedule(body: ReportScheduleIn, db: AsyncSession = DbDep) -> dict:
    """保存周报推送计划（写操作仅管理员，路由级 trim 鉴权强校验）。"""
    cfg = await report_digest.save_schedule(db, {"enabled": body.enabled, "weekday": body.weekday, "hour": body.hour})
    cfg["last_run"] = await report_digest.last_run_date(db) or None
    return cfg


@router.post("/report/send")
async def send_report_now(db: AsyncSession = DbDep) -> dict:
    """立即生成并广播周报（调试/验收按钮；仅管理员）。

    Args:
        db (AsyncSession): 请求级会话。

    Returns:
        dict: {digest: 摘要文本}（前端回显，渠道侧同文推送）。
    """
    return {"digest": await report_digest.push_now(db)}
