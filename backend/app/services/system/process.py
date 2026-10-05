"""进程管理与安全白名单（契约 §2.13：protected 命中即拒绝 kill → 1004）。"""

from __future__ import annotations

import asyncio
import fnmatch

import psutil
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError
from app.models.system import KillWhitelist

# 内置受保护系统进程（不可终止）；支持 fnmatch 通配（fnos-* 保护全部飞牛服务）
PROTECTED_NAMES = {"systemd", "init", "kernel", "sshd", "uvicorn", "python3", "fnos-*"}


def _is_protected(name: str, whitelist: set[str]) -> bool:
    """进程名是否命中保护名单（内置 fnmatch 通配 ∪ 用户白名单精确匹配）。

    Args:
        name (str): 进程名。
        whitelist (set[str]): 用户白名单（DB KillWhitelist 名单，精确匹配）。

    Returns:
        bool: 命中内置 PROTECTED_NAMES 通配或用户白名单时 True。
    """
    low = name.lower()
    if any(fnmatch.fnmatch(low, p.lower()) for p in PROTECTED_NAMES):
        return True
    return any(low == w.lower() for w in whitelist)


async def list_processes(db: AsyncSession, sort: str, limit: int) -> list[dict]:
    """进程清单（CPU/内存排序），附保护标记供前端禁用 kill 按钮。

    Args:
        db (AsyncSession): 请求级会话（读 KillWhitelist）。
        sort (str): 排序键，"cpu" 按 CPU%，其余按内存%。
        limit (int): 返回条数上限。

    Returns:
        list[dict]: 进程条目列表，每项含 pid/name/exe/cmdline/user/
        cpu_percent/mem_percent/mem_rss_mb/status/protected。
    """
    result = await db.execute(select(KillWhitelist))
    whitelist = {row.name for row in result.scalars()}

    items = []
    fields = ["pid", "name", "exe", "cmdline", "username", "memory_percent", "memory_info", "status"]
    for proc in psutil.process_iter(fields):
        try:
            info = proc.info
            with proc.oneshot():
                cpu = proc.cpu_percent(None)
            mem_info = info.get("memory_info")
            name = info.get("name") or ""
            cmdline = " ".join(info.get("cmdline") or [])[:500] or None
            items.append(
                {
                    "pid": info["pid"],
                    "name": name,
                    "exe": info.get("exe"),
                    "cmdline": cmdline,
                    "user": info.get("username"),
                    "cpu_percent": round(cpu, 1),
                    "mem_percent": round(info.get("memory_percent") or 0.0, 1),
                    "mem_rss_mb": round((mem_info.rss if mem_info else 0) / 1024 / 1024, 1),
                    "status": info.get("status") or "?",
                    "protected": _is_protected(name, whitelist),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    items.sort(key=lambda p: p["cpu_percent"] if sort == "cpu" else p["mem_percent"], reverse=True)
    return items[:limit]


async def kill_process(db: AsyncSession, pid: int, confirm: bool) -> dict:
    """终止进程：SIGTERM 5s 未退升级 SIGKILL；保护名单进程拒绝（契约 §2.13）。

    Args:
        db (AsyncSession): 请求级会话（读 KillWhitelist）。
        pid (int): 目标进程 id。
        confirm (bool): 必须显式 True 才执行。

    Returns:
        dict: {pid, name, killed: True}。

    Raises:
        PermissionDeniedError: confirm 非 True，或进程在保护名单内。
        NotFoundError: pid 对应进程不存在。
    """
    if not confirm:
        raise PermissionDeniedError("kill 需要 confirm=true")
    try:
        proc = psutil.Process(pid)
        name = proc.name() or ""
    except psutil.NoSuchProcess as exc:
        from app.core.exceptions import NotFoundError

        raise NotFoundError(f"process {pid} not found") from exc
    result = await db.execute(select(KillWhitelist))
    whitelist = {row.name for row in result.scalars()}
    if _is_protected(name, whitelist):
        raise PermissionDeniedError(f"进程 {name} 在保护名单内，禁止终止")
    try:
        proc.terminate()
        await asyncio.to_thread(proc.wait, timeout=5)
    except psutil.NoSuchProcess:
        pass
    except psutil.TimeoutExpired:
        # SIGTERM 5s 未退：升级 SIGTERM→SIGKILL 并等待回收，否则进程残留且 API 500
        proc.kill()
        try:
            await asyncio.to_thread(proc.wait, timeout=3)
        except psutil.TimeoutExpired:
            pass
    return {"pid": pid, "name": name, "killed": True}
