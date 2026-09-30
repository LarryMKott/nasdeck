"""三档磁盘自检引擎（进程内状态，重启即失；契约 §2.7/§3.2）。

真实执行依赖 smartctl -t；本服务负责互斥/状态机/进度模拟落点，
smartctl 缺失时发起自检抛 1003（接口层转换）。
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from app.core.exceptions import StateConflictError

_DURATION_MIN = {"short": 2, "long": 240, "conveyance": 5}
_tests: dict[str, dict] = {}
_task: dict[str, asyncio.Task] = {}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def list_tests() -> list[dict]:
    return [dict(v, device=k) for k, v in _tests.items()]


def get_test(device: str) -> dict:
    if device not in _tests:
        raise KeyError(device)
    return dict(_tests[device], device=device)


def start_test(device: str, test_type: str, runner) -> dict:
    """runner(device, on_progress, on_done) 为 smartctl 执行器，由 API 层注入。"""
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
        total = _DURATION_MIN.get(test_type, 2) * 60
        try:
            await runner(device, test_type)
            # 真机 smartctl 为异步后台自检：命令成功即进入 running，由轮询更新结果；
            # 此处保留进度推进协程，超时兜底标记完成。
            started = time.monotonic()
            while time.monotonic() - started < total and _tests.get(device) is state:
                state["percent"] = min(int((time.monotonic() - started) / total * 100), 99)
                await asyncio.sleep(5)
            if _tests.get(device) is state:
                state.update(status="done", percent=100, completed_at=_now(), result="completed")
        except Exception as exc:  # noqa: BLE001 执行失败落状态
            state.update(status="failed", completed_at=_now(), error=str(exc)[:200])

    _task[device] = asyncio.create_task(_run())
    return dict(state)


def stop_test(device: str) -> None:
    task = _task.pop(device, None)
    if task:
        task.cancel()
    state = _tests.get(device)
    if state and state["status"] == "running":
        state.update(status="failed", completed_at=_now(), error="aborted")
