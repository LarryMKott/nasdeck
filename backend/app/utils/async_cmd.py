"""异步命令执行封装：统一超时与缺失工具的错误码（1003）。"""

from __future__ import annotations

import asyncio
import shutil

from app.core.config import settings
from app.core.exceptions import ExternalToolError


async def run_cmd(
    *args: str, timeout: float = 15.0
) -> tuple[int, str, str]:
    """执行命令返回 (rc, stdout, stderr)；命令不存在抛 1003。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise ExternalToolError(f"command not found: {args[0]}") from exc
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as exc:
        proc.kill()
        raise ExternalToolError(f"command timeout: {args[0]}") from exc
    return (
        proc.returncode or 0,
        out.decode(errors="replace"),
        err.decode(errors="replace"),
    )


async def run_storcli(*args: str, timeout: float = 30.0) -> tuple[int, str, str]:
    """storcli 封装：按配置路径/PATH 探测。"""
    if not shutil.which(settings.storcli_cmd):
        raise ExternalToolError("storcli not available")
    return await run_cmd(settings.storcli_cmd, *args, timeout=timeout)


def run_cmd_sync(*args: str, timeout: float = 15.0) -> tuple[int, str, str]:
    """同步版命令执行：专供线程池内的 storcli 采集路径（asyncio 不可用场景）。"""
    import subprocess

    try:
        proc = subprocess.run(  # noqa: S603 参数由内部调用方白名单构造
            list(args), capture_output=True, timeout=timeout, check=False
        )
    except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
        raise ExternalToolError(f"command not executable: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ExternalToolError(f"command timeout: {args[0]}") from exc
    return (
        proc.returncode or 0,
        proc.stdout.decode(errors="replace"),
        proc.stderr.decode(errors="replace"),
    )


def run_storcli_sync(*args: str, timeout: float = 30.0) -> tuple[int, str, str]:
    """storcli 同步封装（与 run_storcli 同探测顺序）。"""
    from app.core.config import settings

    return run_cmd_sync(settings.storcli_cmd, *args, timeout=timeout)
