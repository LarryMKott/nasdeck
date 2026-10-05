"""三档磁盘自检引擎（进程内状态，重启即失；契约 §2.7/§3.2）。

真实执行依赖 smartctl -t；本服务负责互斥/状态机/进度模拟落点，
smartctl 缺失时发起自检抛 1003（接口层转换）。
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from app.core.exceptions import StateConflictError
from app.utils.async_cmd import run_cmd

_DURATION_MIN = {"short": 2, "long": 240, "conveyance": 5}
_tests: dict[str, dict] = {}
_task: dict[str, asyncio.Task] = {}


def _now() -> str:
    """当前 UTC 时刻 → 状态时间戳统一口径的 ISO 墙钟串。

    Returns:
        str: 形如 ``YYYY-MM-DDTHH:MM:SS+00:00`` 的时间串。
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


async def smartctl_runner(device: str, test_type: str) -> None:
    """发起 smartctl -t（异步后台自检，命令成功即已开始）。

    Args:
        device (str): 不带 /dev/ 前缀的设备名。
        test_type (str): 自检类型（short/long/conveyance）。

    Raises:
        RuntimeError: smartctl 返回码非 0/2（视为不受理；stderr 截断至 200 字符）。
    """
    rc, _out, err = await run_cmd("smartctl", "-t", test_type, f"/dev/{device}", timeout=120)
    if rc not in (0, 2):
        raise RuntimeError(err.strip()[:200] or f"smartctl -t rc={rc}")


async def smartctl_probe(device: str) -> tuple[str, str | None]:
    """解析 smartctl -l selftest 最后一条记录 → (result, error)。

    只在预计时长到点后调用：此时本次自检大概率已写入日志，最后一条即本次，
    不做进行中轮询（日志无时间戳，轮询易把历史记录误判为本次结果）。

    Args:
        device (str): 不带 /dev/ 前缀的设备名。

    Returns:
        tuple[str, str | None]: (result, error)；result ∈ completed/failed/aborted/unknown，
            error 为面向用户的说明文案（正常完成时为 None）。
    """
    rc, out, _err = await run_cmd("smartctl", "-l", "selftest", f"/dev/{device}", timeout=30)
    entries = [ln for ln in out.splitlines() if ln.lstrip().startswith("#")]
    if not entries:
        return "unknown", f"自检日志为空或不可读（smartctl rc={rc}）"
    last = entries[-1].lower()
    if "in progress" in last:
        return "unknown", "自检仍在进行，稍后刷新查看 smartctl 日志"
    if "completed without error" in last:
        return "completed", None
    if "aborted" in last or "interrupted" in last:
        return "aborted", "自检被中止（详情见 smartctl -l selftest）"
    if "completed" in last:  # Completed: read failure 等带错误的完成
        return "failed", "自检完成但报告错误（详情见 smartctl -l selftest）"
    return "unknown", None


def list_tests() -> list[dict]:
    """列出全部盘的自检状态（进程内状态机，重启即失）。

    Returns:
        list[dict]: 状态字典列表，每项附 device 字段。
    """
    return [dict(v, device=k) for k, v in _tests.items()]


def get_test(device: str) -> dict:
    """查询单盘自检状态。

    Args:
        device (str): 设备名。

    Returns:
        dict: 状态字典（附 device 字段）。

    Raises:
        KeyError: 该盘无自检记录（接口层转 404）。
    """
    if device not in _tests:
        raise KeyError(device)
    return dict(_tests[device], device=device)


def start_test(device: str, test_type: str, runner=None, probe=None) -> dict:
    """发起单盘自检并注册进程内状态机，返回初始状态。

    runner(device, test_type) 为 smartctl -t 执行器、probe(device) 为结果查询器
    （返回 (result, error)），缺省用本模块的 smartctl 实现（API 层此前内联，收敛至此
    供周期巡检调度复用）。

    Args:
        device (str): 不带 /dev/ 前缀的设备名。
        test_type (str): 自检类型（short/long/conveyance）。
        runner (Callable | None): 自检执行器；None 用本模块 smartctl_runner。
        probe (Callable | None): 结果查询器；None 用本模块 smartctl_probe。

    Returns:
        dict: 初始状态副本（status="running"、percent=0）。

    Raises:
        StateConflictError: 该盘已有 running 自检（互斥，接口层转 409）。
    """
    runner = runner or smartctl_runner
    probe = probe or smartctl_probe
    running = [d for d, t in _tests.items() if t["status"] == "running"]
    if device in running:
        raise StateConflictError(f"self-test already running on {device}")
    state = {
        "device": device,
        "type": test_type,
        "status": "running",
        "started_at": _now(),
        "completed_at": None,
        "percent": 0,
        "result": None,
        "error": None,
    }
    _tests[device] = state

    async def _run() -> None:
        """单盘自检后台任务：推进度 → 到点 probe 判定真实结果（详见模块 docstring）。"""
        total = _DURATION_MIN.get(test_type, 2) * 60
        try:
            await runner(device, test_type)
            # 真机 smartctl 为异步后台自检：命令成功即进入 running。按预计时长推进
            # 进度，到点后经 probe 查询真实自检日志（smartctl -l selftest 最后一条）
            # 判定结果——任务被盘中止/报错不得谎报 completed（审查 2026-09-30 P2）。
            started = time.monotonic()
            while time.monotonic() - started < total and _tests.get(device) is state:
                state["percent"] = min(int((time.monotonic() - started) / total * 100), 99)
                await asyncio.sleep(5)
            if _tests.get(device) is state:
                result, error = "unknown", "无法确认自检结果，请查看 smartctl 自检日志"
                if probe is not None:
                    try:
                        result, error = await probe(device)
                    except Exception as exc:  # noqa: BLE001 查询失败不掩盖状态机
                        result, error = "unknown", str(exc)[:200]
                state.update(
                    status="done", percent=100, completed_at=_now(), result=result, error=error
                )
        except Exception as exc:  # noqa: BLE001 执行失败落状态
            state.update(status="failed", completed_at=_now(), error=str(exc)[:200])

    _task[device] = asyncio.create_task(_run())
    return dict(state)
