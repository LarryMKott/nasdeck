"""硬件采集策略决策层单测（契约 §2.1 低占用架构的启动决策）。"""

from __future__ import annotations

from app.services.hardware import policy as policy_mod
from app.services.hardware.policy import HardwarePolicy, decide, get_policy, set_policy

# 探测点 → 期望创建的形态（目录或文本文件）
_PROBES = {
    "PROC_STAT": ("stat", "file"),
    "PROC_MEMINFO": ("meminfo", "file"),
    "SYS_CPUFREQ": ("freq", "file"),
    "SYS_DRM": ("drm", "dir"),
}


def _patch_probes(monkeypatch, tmp_path, stat=True, meminfo=True, freq=True, drm=True):
    """按需创建探测点文件/目录，并把决策层常量指过去。"""
    want = {"PROC_STAT": stat, "PROC_MEMINFO": meminfo, "SYS_CPUFREQ": freq, "SYS_DRM": drm}
    for key, (name, kind) in _PROBES.items():
        path = tmp_path / name
        if want[key]:
            path.mkdir() if kind == "dir" else path.write_text("x")
        monkeypatch.setattr(policy_mod, key, str(path))


def test_decide_linux_full(tmp_path, monkeypatch):
    _patch_probes(monkeypatch, tmp_path, stat=True, meminfo=True, freq=True, drm=True)
    monkeypatch.setattr(policy_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        policy_mod.shutil, "which", lambda name: "/usr/bin/x" if name in ("smartctl", "nvidia-smi") else None
    )
    p = decide()
    assert (p.cpu_util, p.cpu_freq, p.memory) == ("proc", "sysfs", "meminfo")
    assert p.gpu_scan is True
    assert p.gpu_vendors == {"amd": "sysfs", "nvidia": "nvidia-smi", "intel": "unavailable"}
    assert p.tools["smartctl"] and p.tools["nvidia-smi"] and not p.tools["lspci"]
    # reasons 记录各探测点结论（降级判定留档）
    assert "cpu_util" in p.reasons and "gpu_scan" in p.reasons


def test_decide_degraded_reasons(tmp_path, monkeypatch):
    _patch_probes(monkeypatch, tmp_path, stat=False, drm=True)
    monkeypatch.setattr(policy_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(policy_mod.shutil, "which", lambda name: None)
    p = decide()
    assert p.cpu_util == "psutil"
    assert "缺失" in p.reasons["cpu_util"]  # 降级判定留档可读


def test_decide_no_kernel_files(tmp_path, monkeypatch):
    _patch_probes(monkeypatch, tmp_path, stat=False, meminfo=False, freq=False, drm=False)
    monkeypatch.setattr(policy_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(policy_mod.shutil, "which", lambda name: None)
    p = decide()
    assert (p.cpu_util, p.cpu_freq, p.memory) == ("psutil", "psutil", "psutil")
    assert p.gpu_scan is False
    assert set(p.gpu_vendors.values()) == {"unavailable"}


def test_decide_nvidia_requires_tool(tmp_path, monkeypatch):
    _patch_probes(monkeypatch, tmp_path, drm=True)
    monkeypatch.setattr(policy_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(policy_mod.shutil, "which", lambda name: None)  # nvidia-smi 不在位
    p = decide()
    assert p.gpu_vendors["nvidia"] == "unavailable"
    assert p.gpu_vendors["amd"] == "sysfs"


def test_get_policy_singleton(monkeypatch):
    calls = []

    def fake_decide() -> HardwarePolicy:
        calls.append(1)
        return HardwarePolicy(
            platform="Test", cpu_util="proc", cpu_freq="sysfs", memory="meminfo",
            gpu_scan=False, gpu_vendors={},
        )

    monkeypatch.setattr(policy_mod, "_policy", None)  # 测试后自动还原
    monkeypatch.setattr(policy_mod, "decide", fake_decide)
    assert get_policy() is get_policy()
    assert len(calls) == 1
    set_policy(None)  # 显式重置后再次取用须重新决策
    get_policy()
    assert len(calls) == 2
