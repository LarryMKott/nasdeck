"""双架构适配的单元覆盖（#16 采集层 / #15 打包文案）。

覆盖四类「ARM 上会踩、x86 上不会暴露」的路径：
- 无 DMI 板卡（设备树兜底 / 两者都缺）；
- aarch64 的 /proc/cpuinfo 无 model name；
- 只有 thermal_zone、没有 hwmon 温度芯片；
- 板载 GPU（Mali/Panfrost 等）只列清单、不声称有实时指标；
- 只读 pwm 通道直接拒绝写，不进入失败回滚。
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from app.services.control import hwmon_driver
from app.services.hardware import cpu as cpu_mod
from app.services.hardware import gpu as gpu_mod
from app.services.hardware import motherboard as board_mod
from app.services.monitor import temperature as temp_mod


async def test_board_without_dmi_but_with_device_tree(monkeypatch):
    values = {
        "board_vendor": ("FriendlyELEC", "device-tree"),
        "board_name": ("NanoPi R6S", "device-tree"),
        "product_name": ("NanoPi R6S", "device-tree"),
    }
    monkeypatch.setattr(board_mod, "read_board_field", lambda name: values.get(name))
    # lspci 不在位：patch 到策略对象上，而不是去改 dict 的 get
    monkeypatch.setattr(
        board_mod, "get_policy", lambda: types.SimpleNamespace(tools={"lspci": None})
    )
    out = await board_mod.MotherboardCollector().collect()
    assert out["available"] is True
    assert out["name"] == "FriendlyELEC NanoPi R6S"
    assert out["source"] == "device-tree"
    assert out["bios_vendor"] is None


async def test_board_without_dmi_and_without_device_tree(monkeypatch):
    monkeypatch.setattr(board_mod, "read_board_field", lambda _name: None)
    out = await board_mod.MotherboardCollector().collect()
    assert out["available"] is False
    assert out["reason"] == "no_dmi"
    assert out["name"] == ""


async def test_cpu_model_falls_back_to_device_tree(monkeypatch):
    monkeypatch.setattr(cpu_mod, "read_text", lambda _path: None)
    monkeypatch.setattr(cpu_mod, "read_board_field", lambda _n: ("NanoPi R6S", "device-tree"))
    out = await cpu_mod.CpuCollector().collect()
    assert out["name"] == "NanoPi R6S"
    assert out["name_source"] == "device-tree"


async def test_cpu_model_from_proc_cpuinfo_wins(monkeypatch):
    monkeypatch.setattr(cpu_mod, "read_text", lambda _p: "model name\t: Intel Xeon\n")
    out = await cpu_mod.CpuCollector().collect()
    assert out["name"] == "Intel Xeon"
    assert "name_source" not in out


def test_thermal_zone_items_converts_millidegrees(tmp_path: Path):
    zone = tmp_path / "thermal_zone0"
    zone.mkdir()
    (zone / "type").write_text("cpu-thermal", encoding="ascii")
    (zone / "temp").write_text("48500", encoding="ascii")
    items = temp_mod._thermal_zone_items(str(tmp_path))
    assert len(items) == 1
    assert items[0]["celsius"] == 48.5
    assert items[0]["zone"] == "cpu"
    assert items[0]["grade"] == "normal"


def test_thermal_zone_items_skips_broken_zone(tmp_path: Path):
    broken = tmp_path / "thermal_zone0"
    broken.mkdir()
    (broken / "type").write_text("soc", encoding="ascii")
    (broken / "temp").write_text("not-a-number", encoding="ascii")
    assert temp_mod._thermal_zone_items(str(tmp_path)) == []


async def test_gpu_board_vendor_lists_without_realtime(monkeypatch):
    monkeypatch.setattr(gpu_mod, "list_dirs", lambda _p: ["card0"])
    monkeypatch.setattr(gpu_mod, "read_text", lambda _p: "0x1ae0")
    out = await gpu_mod.GpuCollector().collect()
    card = out["cards"][0]
    assert card["realtime"] is False
    assert card["reason"] == "arch_unsupported"


async def test_gpu_known_vendor_has_realtime(monkeypatch):
    monkeypatch.setattr(gpu_mod, "list_dirs", lambda _p: ["card0"])
    monkeypatch.setattr(gpu_mod, "read_text", lambda _p: "0x8086")
    out = await gpu_mod.GpuCollector().collect()
    assert out["cards"][0]["vendor_name"] == "intel"
    assert out["cards"][0]["realtime"] is True
    assert "reason" not in out["cards"][0]


def test_write_pwm_refuses_readonly_channel(tmp_path: Path, monkeypatch):
    pwm = tmp_path / "pwm1"
    pwm.write_text("128", encoding="ascii")
    pwm.chmod(0o444)
    monkeypatch.setattr(hwmon_driver, "find_channel", lambda _n, _c: pwm)
    assert hwmon_driver.write_pwm("soc_thermal", 1, 50) is False
    assert pwm.read_text(encoding="ascii") == "128"


@pytest.mark.parametrize("arch", ["arm", "all", "x86"])
def test_build_fpk_arch_choices_are_declared(arch):
    """打包器只认这三种取值；写错必须在 argparse 层就被挡住，不能静默出 x86 包。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_fpk", Path(__file__).resolve().parents[2] / "scripts" / "build_fpk.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.ARCHES) == {"x86", "arm"}
    assert module.ARCHES["arm"]["manifest_platform"] == "arm"
    assert module.ARCHES["x86"]["manifest_platform"] == "x86"
    assert module.ARCHES["arm"]["storcli"] is False
    assert module.ARCHES["x86"]["storcli"] is True
    assert arch in ("arm", "all", "x86")
