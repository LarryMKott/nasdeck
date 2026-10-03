"""Docker 容器监控：unix socket 访问 docker engine API；不可用即降级（契约 §2.11）。"""

from __future__ import annotations

import json
from pathlib import Path

SOCKET = Path("/var/run/docker.sock")


def docker_available() -> str | None:
    """可用返回 None，否则返回不可用原因。"""
    import platform

    if platform.system() != "Linux":
        return "docker 仅在 Linux 主机可用"
    if not SOCKET.exists():
        return "docker socket 不存在"
    return None


async def list_containers() -> dict:
    reason = docker_available()
    if reason:
        return {"available": False, "reason": reason, "containers": []}
    import asyncio
    import contextlib

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "--format", "{{json .}}", "--no-trunc",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
    except (FileNotFoundError, TimeoutError):
        # 超时须回收子进程：daemon 卡顿时每次刷新泄漏一个 docker 进程
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.kill()
                await proc.wait()
        return {"available": False, "reason": "docker CLI 不可用", "containers": []}
    containers = []
    for line in stdout.decode().splitlines():
        if not line.strip():
            continue
        try:
            c = json.loads(line)
        except ValueError:
            continue
        containers.append(
            {
                "id": c.get("ID", "")[:12],
                "name": c.get("Names", ""),
                "image": c.get("Image", ""),
                "state": c.get("State", ""),
                "status": c.get("Status", ""),
                "created": c.get("CreatedAt", ""),
                "ports": [p for p in (c.get("Ports") or "").split(",") if p],
            }
        )
    return {"available": True, "reason": None, "containers": containers}
