"""异步命令执行封装：统一超时与缺失工具的错误码（1003）。

DEBUG 级别记录每次外部工具调用的完整命令行、退出码、输出量与耗时——
这是「系统信息获取情况」排障的主线索（smartctl/storcli/sensors/mdadm 等）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from app.core.exceptions import ExternalToolError

logger = logging.getLogger(__name__)


def _log_call(prefix: str, args: tuple[str, ...], rc: int, out: str, err: str, elapsed: float) -> None:
    logger.debug(
        "%s %s → rc=%s out=%dB err=%dB %.2fs",
        prefix,
        " ".join(args),
        rc,
        len(out),
        len(err),
        elapsed,
    )


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
        logger.debug("工具缺失 %s: %s", args[0], exc)
        raise ExternalToolError(f"command not found: {args[0]}") from exc
    started = time.monotonic()
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as exc:
        proc.kill()
        # kill 后回收：不 wait 会留下僵尸进程表项与管道句柄，等 GC/child watcher 兜底
        with contextlib.suppress(Exception):
            await proc.wait()
        logger.debug("工具超时 %s（>%gs）", args[0], timeout)
        raise ExternalToolError(f"command timeout: {args[0]}") from exc
    out_text, err_text = out.decode(errors="replace"), err.decode(errors="replace")
    _log_call("工具", args, proc.returncode or 0, out_text, err_text, time.monotonic() - started)
    return (proc.returncode or 0, out_text, err_text)


def run_cmd_sync(*args: str, timeout: float = 15.0) -> tuple[int, str, str]:
    """同步版命令执行：专供线程池内的 storcli 采集路径（asyncio 不可用场景）。"""
    import subprocess

    started = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603 参数由内部调用方白名单构造
            list(args), capture_output=True, timeout=timeout, check=False
        )
    except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
        logger.debug("工具缺失 %s: %s", args[0], exc)
        raise ExternalToolError(f"command not executable: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        logger.debug("工具超时 %s（>%gs）", args[0], timeout)
        raise ExternalToolError(f"command timeout: {args[0]}") from exc
    out, err = proc.stdout.decode(errors="replace"), proc.stderr.decode(errors="replace")
    _log_call("工具", args, proc.returncode or 0, out, err, time.monotonic() - started)
    return (proc.returncode or 0, out, err)


def run_storcli_sync(*args: str, timeout: float = 30.0) -> tuple[int, str, str]:
    """storcli 同步封装：按配置路径/PATH 解析命令（settings.storcli_cmd）。"""
    from app.core.config import settings

    return run_cmd_sync(settings.storcli_cmd, *args, timeout=timeout)
