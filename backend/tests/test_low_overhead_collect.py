"""低占用采集链路单测：/proc/stat 差值、GPU sysfs 直读与 nvidia-smi 解析（契约 §2.1）。"""

from __future__ import annotations

from app.services.hardware import policy as policy_mod
from app.services.hardware.policy import HardwarePolicy
from app.services.monitor import gpu as gpu_service
from app.services.monitor import system_resources as sr


def _inject_policy(monkeypatch, **overrides):
    """注入决策层策略（monkeypatch 自动还原）；默认 Linux 全 proc 策略、GPU 全不可用。"""
    base = dict(
        platform="Linux",
        cpu_util="proc",
        cpu_freq="sysfs",
        memory="meminfo",
        gpu_scan=False,
        gpu_vendors={"amd": "unavailable", "nvidia": "unavailable", "intel": "unavailable"},
    )
    base.update(overrides)
    monkeypatch.setattr(policy_mod, "_policy", HardwarePolicy(**base))


def test_read_proc_stat_rows(tmp_path):
    f = tmp_path / "stat"
    f.write_text(
        "cpu  100 0 100 800 0 0 0 0 0 0\n"
        "cpu0 100 0 100 800 0 0 0 0 0 0\n"
        "intr 123\n",  # 非 cpu 行终止
        encoding="ascii",
    )
    # total = user+nice+system+idle+iowait+irq+softirq+steal = 1000；idle = idle+iowait = 800
    assert sr._read_proc_stat(str(f)) == [(1000, 800), (1000, 800)]


def test_cpu_percent_delta(monkeypatch):
    _inject_policy(monkeypatch)
    monkeypatch.setattr(sr, "_cpu_stat_last", {"rows": None})
    rows_t0 = [(1000, 800), (100, 80)]
    rows_t1 = [(2000, 1650), (200, 165)]  # 合计与核0 均 busy 15%
    monkeypatch.setattr(sr, "_read_proc_stat", lambda path="/proc/stat": rows_t0)
    assert sr._cpu_percent() == (0.0, [0.0])  # 首采为 0（与 psutil 同语义）
    monkeypatch.setattr(sr, "_read_proc_stat", lambda path="/proc/stat": rows_t1)
    assert sr._cpu_percent() == (15.0, [15.0])


def test_cpu_percent_core_count_change_resets(monkeypatch):
    _inject_policy(monkeypatch)
    monkeypatch.setattr(sr, "_cpu_stat_last", {"rows": [(100, 50)]})
    monkeypatch.setattr(
        sr, "_read_proc_stat", lambda path="/proc/stat": [(100, 50), (100, 50), (100, 50)]
    )
    assert sr._cpu_percent() == (0.0, [0.0, 0.0])  # 核数变化重置，防跨轮错差


def test_cpu_percent_psutil_strategy(monkeypatch):
    """策略判定 psutil（非 Linux）时不读 /proc/stat，走 psutil 分支。"""
    _inject_policy(monkeypatch, platform="Windows", cpu_util="psutil", cpu_freq="psutil", memory="psutil")
    called = []
    monkeypatch.setattr(sr, "_read_proc_stat", lambda path="/proc/stat": called.append(path))
    monkeypatch.setattr(sr.psutil, "cpu_percent", lambda **kw: [12.0] if kw.get("percpu") else 12.0)
    assert sr._cpu_percent() == (12.0, [12.0])
    assert not called  # 决策为 psutil 就不再探测 proc


def test_parse_nvidia_smi():
    gpus = gpu_service._parse_nvidia_smi("RTX 3060, 45, 2048, 8192, 55\n")
    assert gpus[0]["name"] == "RTX 3060"
    assert gpus[0]["percent"] == 45.0
    assert gpus[0]["vram_total_mb"] == 8192.0
    assert gpus[0]["temp_c"] == 55.0
    gpus = gpu_service._parse_nvidia_smi("Intel Xe, [N/A], [N/A], [N/A], [N/A]\n")
    assert gpus[0]["percent"] is None


def test_amd_card_sysfs(tmp_path):
    dev = tmp_path / "card0" / "device"
    (dev / "hwmon" / "hwmon2").mkdir(parents=True)
    (dev / "gpu_busy_percent").write_text("37\n")
    (dev / "mem_info_vram_used").write_text("8589934592\n")  # 8 GiB
    (dev / "mem_info_vram_total").write_text("17179869184\n")  # 16 GiB
    (dev / "hwmon" / "hwmon2" / "temp1_input").write_text("52000\n")  # 52.0 ℃
    assert gpu_service._amd_card(str(dev)) == {
        "percent": 37,
        "vram_used_mb": 8192.0,
        "vram_total_mb": 16384.0,
        "temp_c": 52.0,
    }


def test_scan_cards_filters_unknown_vendor(tmp_path, monkeypatch):
    _inject_policy(
        monkeypatch,
        gpu_scan=True,
        gpu_vendors={"amd": "sysfs", "nvidia": "nvidia-smi", "intel": "unavailable"},
    )
    monkeypatch.setattr(gpu_service, "_scan_cache", {"ts": 0.0, "cards": None})
    base = tmp_path / "drm"
    for name, vendor in (("card0", "0x1002"), ("card1", "0x9999"), ("renderD128", "0x10de")):
        d = base / name / "device"
        d.mkdir(parents=True)
        (d / "vendor").write_text(vendor + "\n")
    cards = gpu_service._scan_cards(str(base))
    assert [c["name"] for c in cards] == ["card0"]
    assert cards[0]["kind"] == "amd"


def test_collect_skips_scan_when_policy_denies(monkeypatch):
    """策略判定无 drm（gpu_scan=False）时直接不可用，不枚举不 fork。"""
    _inject_policy(monkeypatch)  # gpu_scan=False
    monkeypatch.setattr(gpu_service, "_cache", {"ts": 0.0, "data": None})

    async def _fail_scan(base="/sys/class/drm"):
        raise AssertionError("策略拒绝时不应扫描")

    monkeypatch.setattr(gpu_service, "_scan_cards", _fail_scan)

    import asyncio

    result = asyncio.run(gpu_service.collect())
    assert result["available"] is False and result["percent"] is None
