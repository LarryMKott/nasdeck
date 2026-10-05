"""Docker 容器监控：unix socket 访问 docker engine API；不可用即降级（契约 §2.11）。

资源用量（M2.2）：cgroup 直读零额外 fork——附着在 list_containers 已有的
docker ps 一轮上，按容器 cgroup 目录读 cpu/memory，进程内上次采样算 CPU 增速；
首轮无增量返回 null（合法真值）。cgroup v2 优先，v1 路径回退，两者皆无则该列 null。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

SOCKET = Path("/var/run/docker.sock")
_CGROUP_V2_ROOT = Path("/sys/fs/cgroup")
# 上次采样：cid12 → (usage_usec, monotonic)；容器重建后 id 变化自然失效
_prev_cpu: dict[str, tuple[int, float]] = {}


def docker_available() -> str | None:
    """探测 docker 引擎是否可用。

    Returns:
        str | None: 可用返回 None，否则返回不可用原因（非 Linux 主机 /
            docker socket 不存在）。
    """
    import platform

    if platform.system() != "Linux":
        return "docker 仅在 Linux 主机可用"
    if not SOCKET.exists():
        return "docker socket 不存在"
    return None


def _read_int(path: Path) -> int | None:
    """读 cgroup 数值文件里的首个整数。

    Args:
        path (Path): cgroup 数值文件路径（如 memory.current）。

    Returns:
        int | None: 文件首行首个整数；文件不可读或无整数时 None。
    """
    try:
        return int(path.read_text().strip().splitlines()[0].split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _cgroup_stats(full_id: str) -> tuple[int | None, int | None]:
    """容器 full id → (cpu usage_usec, memory working set bytes)。

    cgroup v2 优先，v1 路径回退，两者皆无返回 (None, None)。
    """
    v2 = _CGROUP_V2_ROOT / "system.slice" / f"docker-{full_id}.scope"
    if v2.is_dir():
        usage = _stat_key(v2 / "cpu.stat", "usage_usec")  # cpu.stat 为 "KEY VALUE" 行格式
        mem_cur = _read_int(v2 / "memory.current")
        if mem_cur is not None:
            inactive = _stat_key(v2 / "memory.stat", "inactive_file")
            mem_cur = max(mem_cur - (inactive or 0), 0)  # docker stats 口径：working set
        return usage, mem_cur
    v1_cpu = _CGROUP_V2_ROOT / "cpu" / "docker" / full_id
    v1_mem = _CGROUP_V2_ROOT / "memory" / "docker" / full_id
    if v1_cpu.is_dir():
        usage = _read_int(v1_cpu / "cpuacct.usage")
        mem_cur = _read_int(v1_mem / "memory.usage_in_bytes")
        return usage, mem_cur
    return None, None


def _stat_key(stat_file: Path, key: str) -> int | None:
    """从 "KEY VALUE" 行格式的 stat 文件中取指定键的数值。

    Args:
        stat_file (Path): cpu.stat/memory.stat 等文件路径。
        key (str): 目标键名（如 usage_usec、inactive_file）。

    Returns:
        int | None: 键对应数值；文件不可读或键不存在时 None。
    """
    try:
        for line in stat_file.read_text().splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == key:
                return int(parts[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def container_cpu_percent(cid: str, full_id: str) -> float | None:
    """按上次采样增量算容器 CPU%（全核口径，同 docker stats）。

    Args:
        cid (str): 12 位短容器 id（进程内采样缓存键，重建后自然失效）。
        full_id (str): 64 位完整容器 id（定位 cgroup 目录）。

    Returns:
        float | None: CPU 百分比（一位小数）；首轮无增量、容器重建
        （计数器回绕）或时钟异常时 None（合法真值）。
    """
    usage, _mem = _cgroup_stats(full_id)
    if usage is None:
        return None
    now = time.monotonic()
    prev = _prev_cpu.get(cid)
    _prev_cpu[cid] = (usage, now)
    if prev is None:
        return None  # 首轮无增量：合法真值
    prev_usage, prev_ts = prev
    dt = now - prev_ts
    if dt <= 0 or usage < prev_usage:
        return None  # 容器重建（计数器回绕）或时钟异常
    return round((usage - prev_usage) / (dt * 1_000_000) * 100, 1)


def mem_human(bytes_used: int | None) -> str | None:
    """字节数转人类可读字符串（GB/MB/KB/B 自动选单位，一位小数）。

    Args:
        bytes_used (int | None): 内存字节数。

    Returns:
        str | None: 如 "123.4 MB"；入参 None 时返回 None。
    """
    if bytes_used is None:
        return None
    for unit, factor in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if bytes_used >= factor:
            return f"{round(bytes_used / factor, 1)} {unit}"
    return f"{bytes_used} B"


async def list_all_states() -> dict[str, dict] | None:
    """全部容器（含已退出）cid → {name, state, status}；docker 不可用返回 None。

    供退出检测（M2.3）做状态对比：docker ps 默认不显示 exited，必须 -a。
    15s 超时，超时回收子进程防泄漏。

    Returns:
        dict[str, dict] | None: 12 位 cid → {name, state, status}；
        docker 不可用或执行超时时 None。
    """
    reason = docker_available()
    if reason:
        return None
    import asyncio
    import contextlib

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-a", "--format", "{{json .}}", "--no-trunc",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
    except (FileNotFoundError, TimeoutError):
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.kill()
                await proc.wait()
        return None
    states: dict[str, dict] = {}
    for line in stdout.decode().splitlines():
        if not line.strip():
            continue
        try:
            c = json.loads(line)
        except ValueError:
            continue
        states[c.get("ID", "")[:12]] = {
            "name": c.get("Names", ""),
            "state": c.get("State", ""),
            "status": c.get("Status", ""),
        }
    return states


async def list_containers() -> dict:
    """运行中容器列表（附 cgroup 直读的 cpu/memory 用量）。

    15s 超时；超时回收子进程（daemon 卡顿时否则每轮刷新泄漏一个 docker 进程）。

    Returns:
        dict: {available, reason, containers}；containers 每项含 id/name/
        image/state/status/created/ports/cpu_percent/mem_usage；docker
        不可用时 available=False、reason 为原因、containers 为空列表。
    """
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
        full_id = c.get("ID", "")
        cid = full_id[:12]
        cpu_percent, mem_bytes = (None, None)
        if c.get("State") == "running" and full_id:
            cpu_percent = container_cpu_percent(cid, full_id)
            _u, mem_bytes = _cgroup_stats(full_id)
        containers.append(
            {
                "id": cid,
                "name": c.get("Names", ""),
                "image": c.get("Image", ""),
                "state": c.get("State", ""),
                "status": c.get("Status", ""),
                "created": c.get("CreatedAt", ""),
                "ports": [p for p in (c.get("Ports") or "").split(",") if p],
                "cpu_percent": cpu_percent,
                "mem_usage": mem_human(mem_bytes),
            }
        )
    return {"available": True, "reason": None, "containers": containers}
