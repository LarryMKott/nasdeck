"""进程风暴榜采集（花活二期 K）：psutil process_iter 差分 → CPU/内存 Top N。

5s 档（medium_tick 采样进 realtime_cache，fast_tick 并入快照）。CPU 占用为两次
采样 cpu_times 差分（按逻辑核数归一），连续两轮均值去抖；内存取 RSS。口径沿用
端口页（契约 §2.13）：仅进程名 + pid + 占用，不暴露启动路径/参数。
"""

from __future__ import annotations

import time

import psutil

_TOP_N = 8

# 上一轮采样状态：cpu_times 累计秒（差分基准）+ 上一轮平滑结果（两轮均值去抖）
_prev = {"ts": 0.0, "times": {}, "smoothed": {}}


def reset_for_test() -> None:
    """清空差分与平滑状态（测试隔离）。"""
    _prev.update(ts=0.0, times={}, smoothed={})


def _sample_raw() -> tuple[float, dict[int, tuple[str, float, float]]]:
    """一轮原始采样 → (monotonic 时刻, {pid: (进程名, cpu_times 累计秒, rss MB)})。

    进程消失/无权限/僵尸进程跳过；cpu_times 取不到的进程不入榜。
    """
    now = time.monotonic()
    out: dict[int, tuple[str, float, float]] = {}
    for proc in psutil.process_iter(["pid", "name", "cpu_times", "memory_info"]):
        try:
            info = proc.info
            times = info.get("cpu_times")
            if times is None:
                continue
            mem = info.get("memory_info")
            out[info["pid"]] = (
                info.get("name") or "?",
                times.user + times.system,
                (mem.rss / 1024 / 1024) if mem else 0.0,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return now, out


def sample(top_n: int = _TOP_N) -> dict:
    """差分 + 两轮均值去抖 → {cpu: TopN, mem: TopN}（首采 CPU 全 0，内存即报）。

    Args:
        top_n (int): 榜单长度（默认 8）。

    Returns:
        dict: {cpu: [{pid, name, percent}], mem: [{pid, name, rss_mb, percent}]}；
            mem.percent 为占物理内存百分比。
    """
    now, curr = _sample_raw()
    dt = max(now - _prev["ts"], 1e-6)
    cores = psutil.cpu_count(logical=True) or 1
    prev_smooth = _prev["smoothed"]

    rates: dict[int, tuple[str, float, float]] = {}
    for pid, (name, total, rss) in curr.items():
        old_total = _prev["times"].get(pid)
        cpu_pct = max(total - old_total, 0.0) / dt / cores * 100 if old_total is not None else 0.0
        rates[pid] = (name, cpu_pct, rss)

    smoothed: dict[int, tuple[float, float, str]] = {}
    for pid, (name, cpu_pct, rss) in rates.items():
        old = prev_smooth.get(pid)
        pct = (cpu_pct + old[0]) / 2 if old is not None else cpu_pct
        smoothed[pid] = (pct, rss, name)
    _prev.update(ts=now, times={pid: c[1] for pid, c in curr.items()}, smoothed=smoothed)

    total_mb = psutil.virtual_memory().total / 1024 / 1024
    cpu_top = sorted(smoothed.items(), key=lambda kv: kv[1][0], reverse=True)[:top_n]
    mem_top = sorted(smoothed.items(), key=lambda kv: kv[1][1], reverse=True)[:top_n]
    return {
        "cpu": [
            {"pid": pid, "name": name, "percent": round(pct, 1)}
            for pid, (pct, _rss, name) in cpu_top
        ],
        "mem": [
            {"pid": pid, "name": name, "rss_mb": round(rss, 1), "percent": round(rss / total_mb * 100, 1) if total_mb else 0.0}
            for pid, (_pct, rss, name) in mem_top
        ],
    }
