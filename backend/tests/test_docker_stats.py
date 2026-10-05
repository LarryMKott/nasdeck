"""容器 cgroup 资源采集回归：v2 主路径 / v1 回退 / 缺失降级 / CPU 增量口径。"""

from __future__ import annotations

import pytest

from app.services.system import docker


@pytest.fixture
def cgroup_root(tmp_path, monkeypatch):
    root = tmp_path / "cgroup"
    root.mkdir()
    monkeypatch.setattr(docker, "_CGROUP_V2_ROOT", root)
    return root


def _make_v2(root, cid: str, usage_usec: int, mem_cur: int, inactive: int = 0):
    d = root / "system.slice" / f"docker-{cid}.scope"
    d.mkdir(parents=True, exist_ok=True)
    (d / "cpu.stat").write_text(f"usage_usec {usage_usec}\nnr_periods 0\n")
    (d / "memory.current").write_text(f"{mem_cur}\n")
    (d / "memory.stat").write_text(f"anon 1\ninactive_file {inactive}\n")


def _make_v1(root, cid: str, usage_usec: int, mem_bytes: int):
    cpu = root / "cpu" / "docker" / cid
    mem = root / "memory" / "docker" / cid
    cpu.mkdir(parents=True)
    mem.mkdir(parents=True)
    (cpu / "cpuacct.usage").write_text(f"{usage_usec}\n")
    (mem / "memory.usage_in_bytes").write_text(f"{mem_bytes}\n")


def test_v2_stats_working_set(cgroup_root):
    _make_v2(cgroup_root, "a" * 64, usage_usec=1_000_000, mem_cur=500 * 1024**2, inactive=100 * 1024**2)
    usage, mem = docker._cgroup_stats("a" * 64)
    assert usage == 1_000_000
    assert mem == 400 * 1024**2  # 减 inactive_file（docker stats working set 口径）


def test_v1_fallback(cgroup_root):
    _make_v1(cgroup_root, "b" * 64, usage_usec=2_000_000, mem_bytes=300 * 1024**2)
    usage, mem = docker._cgroup_stats("b" * 64)
    assert usage == 2_000_000 and mem == 300 * 1024**2


def test_missing_cgroup_returns_nones(cgroup_root):
    assert docker._cgroup_stats("c" * 64) == (None, None)


def test_cpu_percent_increment_and_first_round_none(cgroup_root, monkeypatch):
    _make_v2(cgroup_root, "d" * 64, usage_usec=1_000_000, mem_cur=1)
    clock = {"t": 100.0}
    monkeypatch.setattr(docker.time, "monotonic", lambda: clock["t"])

    cid = "d" * 12
    assert docker.container_cpu_percent(cid, "d" * 64) is None  # 首轮无增量

    clock["t"] = 105.0
    _make_v2(cgroup_root, "d" * 64, usage_usec=1_000_000 + 12_500_000, mem_cur=1)  # 5s 内 250% CPU（2.5 核）
    assert docker.container_cpu_percent(cid, "d" * 64) == 250.0


def test_cpu_percent_counter_reset_returns_none(cgroup_root, monkeypatch):
    _make_v2(cgroup_root, "e" * 64, usage_usec=1_000_000, mem_cur=1)
    clock = {"t": 100.0}
    monkeypatch.setattr(docker.time, "monotonic", lambda: clock["t"])
    cid = "e" * 12
    docker.container_cpu_percent(cid, "e" * 64)

    clock["t"] = 110.0
    _make_v2(cgroup_root, "e" * 64, usage_usec=500_000, mem_cur=1)  # 容器重建计数回绕
    assert docker.container_cpu_percent(cid, "e" * 64) is None


def test_mem_human_units():
    assert docker.mem_human(None) is None
    assert docker.mem_human(500) == "500 B"
    assert docker.mem_human(5 * 1024**2) == "5.0 MB"
    assert docker.mem_human(int(1.25 * 1024**3)) == "1.2 GB"
