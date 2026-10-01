"""RAPL 功耗采样：energy_uj 差分 / 回绕 / 首样 / 域缺失 / 不可用（monitor/power.py）。"""

from __future__ import annotations

import pytest

from app.services.monitor import power as power_mod


class _FakeClock:
    """替换 power.time 引用，逐次返回预定时刻（不动全局 time 模块）。"""

    def __init__(self, seq: list[float]) -> None:
        self._seq = iter(seq)

    def monotonic(self) -> float:
        return next(self._seq)


PKG = "pkg0"  # Windows 目录名不允许冒号，测试用无冒号名注入（生产为 intel-rapl:0）


def _make_sysfs(tmp_path, package=1_000_000, dram=500_000, rng=10_000_000_000) -> str:
    pkg = tmp_path / PKG
    pkg.mkdir()
    (pkg / "energy_uj").write_text(str(package))
    (pkg / "max_energy_range_uj").write_text(str(rng))
    dram_dir = pkg / "dom-dram"
    dram_dir.mkdir()
    (dram_dir / "name").write_text("dram")
    (dram_dir / "energy_uj").write_text(str(dram))
    (dram_dir / "max_energy_range_uj").write_text(str(rng))
    return str(tmp_path)


def test_unavailable_without_sysfs(tmp_path):
    power_mod._reset()
    r = power_mod.rapl_power(str(tmp_path), pkg=PKG)
    assert r == {"available": False, "watts": None, "cpu_w": None, "dram_w": None}


def test_first_sample_reports_zero_rates(tmp_path):
    root = _make_sysfs(tmp_path)
    power_mod._reset()
    r = power_mod.rapl_power(root, now=1000.0, pkg=PKG)
    assert r["available"] is True
    assert r == {"available": True, "watts": 0.0, "cpu_w": 0.0, "dram_w": 0.0}


def test_rate_delta_over_interval(tmp_path, monkeypatch):
    root = _make_sysfs(tmp_path, package=1_000_000, dram=500_000)
    power_mod._reset()
    monkeypatch.setattr(power_mod, "time", _FakeClock([1000.0, 1001.0]))
    power_mod.rapl_power(root, pkg=PKG)
    pkg = tmp_path / PKG
    (pkg / "energy_uj").write_text(str(1_000_000 + 3_500_000))  # 1s 差 3.5MJ → 3.5W
    (pkg / "dom-dram" / "energy_uj").write_text(str(500_000 + 800_000))
    r = power_mod.rapl_power(root, pkg=PKG)
    assert r["cpu_w"] == pytest.approx(3.5)
    assert r["dram_w"] == pytest.approx(0.8)
    assert r["watts"] == pytest.approx(4.3)


def test_counter_wraparound_adds_range(tmp_path, monkeypatch):
    root = _make_sysfs(tmp_path, package=9_500_000, dram=100, rng=10_000_000)
    power_mod._reset()
    monkeypatch.setattr(power_mod, "time", _FakeClock([2000.0, 2001.0]))
    power_mod.rapl_power(root, pkg=PKG)
    (tmp_path / PKG / "energy_uj").write_text(str(300_000))
    # 回绕：(10_000_000 − 9_500_000) + 300_000 = 800_000 µJ/s → 0.8W
    r = power_mod.rapl_power(root, pkg=PKG)
    assert r["cpu_w"] == pytest.approx(0.8)


def test_missing_dram_domain_keeps_none(tmp_path):
    pkg = tmp_path / PKG
    pkg.mkdir()
    (pkg / "energy_uj").write_text("100")
    (pkg / "max_energy_range_uj").write_text("1000000")
    core = pkg / "dom-core"
    core.mkdir()
    (core / "name").write_text("core")
    power_mod._reset()
    r = power_mod.rapl_power(str(tmp_path), now=5.0, pkg=PKG)
    assert r["available"] is True
    assert r["dram_w"] is None
    assert r["watts"] == 0.0
