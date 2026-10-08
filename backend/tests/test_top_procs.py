"""进程风暴榜单测：cpu_times 差分、两轮均值去抖与 TopN 排序（花活二期 K）。"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.monitor import top_procs


class _FakeProc:
    """psutil.Process 替身：process_iter(fields) 只取 .info。"""

    def __init__(self, pid, name, total, rss_mb):
        self.info = {
            "pid": pid,
            "name": name,
            "cpu_times": SimpleNamespace(user=total / 2, system=total / 2),
            "memory_info": SimpleNamespace(rss=rss_mb * 1024 * 1024),
        }


def _inject(monkeypatch, procs, monotonic, cores=2, total_mb=8192):
    monkeypatch.setattr(top_procs.psutil, "process_iter", lambda fields: procs)
    monkeypatch.setattr(top_procs.psutil, "cpu_count", lambda logical=True: cores)
    monkeypatch.setattr(
        top_procs.psutil, "virtual_memory", lambda: SimpleNamespace(total=total_mb * 1024 * 1024)
    )
    monkeypatch.setattr(top_procs.time, "monotonic", lambda: monotonic)


def test_sample_first_read_cpu_zero_mem_immediate(monkeypatch):
    top_procs.reset_for_test()
    _inject(
        monkeypatch,
        [_FakeProc(1, "a", 10.0, 2048), _FakeProc(2, "b", 0.0, 1024)],
        monotonic=5.0,
    )
    r = top_procs.sample()
    assert r["cpu"][0] == {"pid": 1, "name": "a", "percent": 0.0}  # 首采 CPU 全 0
    assert r["mem"][0]["rss_mb"] == 2048.0  # 内存即报
    assert r["mem"][0]["percent"] == 25.0  # 2048/8192


def test_sample_differential_and_smoothing(monkeypatch):
    top_procs.reset_for_test()
    _inject(monkeypatch, [_FakeProc(1, "a", 10.0, 2048)], monotonic=5.0)
    top_procs.sample()
    # 5s 内 cpu_times 涨 2.0 秒（2 核归一）→ 本轮 20%，与上轮平滑值 0 均值 → 10%
    _inject(monkeypatch, [_FakeProc(1, "a", 12.0, 2048)], monotonic=10.0)
    r = top_procs.sample()
    assert r["cpu"][0]["percent"] == 10.0
    # 再下一轮不涨：本轮 0% 与上轮 10% 均值 → 5%
    _inject(monkeypatch, [_FakeProc(1, "a", 12.0, 2048)], monotonic=15.0)
    assert top_procs.sample()["cpu"][0]["percent"] == 5.0


def test_sample_negative_delta_clamped_and_gone_proc_dropped(monkeypatch):
    top_procs.reset_for_test()
    _inject(monkeypatch, [_FakeProc(1, "a", 10.0, 2048)], monotonic=5.0)
    top_procs.sample()
    # 计数回绕（负差分按 0）+ b 进程新出现（无基准 CPU 0、内存上榜）
    _inject(
        monkeypatch,
        [_FakeProc(1, "a", 4.0, 2048), _FakeProc(2, "b", 100.0, 4096)],
        monotonic=10.0,
    )
    r = top_procs.sample()
    by_pid = {p["pid"]: p for p in r["mem"]}
    assert r["cpu"][0]["percent"] == 0.0  # 负差分钳 0
    assert by_pid[2]["rss_mb"] == 4096.0  # 新进程内存上榜


def test_sample_top_n(monkeypatch):
    top_procs.reset_for_test()
    procs = [_FakeProc(i, f"p{i}", 0.0, 100 + i) for i in range(20)]
    _inject(monkeypatch, procs, monotonic=1.0)
    r = top_procs.sample(top_n=8)
    assert len(r["cpu"]) == 8 and len(r["mem"]) == 8
    assert r["mem"][0]["rss_mb"] == 119.0  # 100+19 最大驻存居首


def test_sample_process_iter_error_skipped(monkeypatch):
    import psutil

    class _DeadProc:
        info = {"pid": 9, "name": "dead", "cpu_times": None, "memory_info": None}

        def __getattr__(self, item):
            raise psutil.NoSuchProcess(pid=9)

    top_procs.reset_for_test()
    _inject(monkeypatch, [_DeadProc(), _FakeProc(1, "a", 0.0, 512)], monotonic=1.0)
    r = top_procs.sample()
    assert [p["pid"] for p in r["mem"]] == [1]  # cpu_times 缺失的进程不入榜
