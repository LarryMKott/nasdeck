"""温度采集扩展：NVMe hwmon 设备定位 + SMART 盘温（monitor/temperature.py）。"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.services.monitor import temperature


def test_nvme_hwmon_items_carry_device_index(monkeypatch, tmp_path):
    hw = tmp_path / "hwmon2"
    hw.mkdir()
    (hw / "name").write_text("nvme", encoding="utf-8")
    (hw / "temp1_input").write_text("56912", encoding="ascii")
    (hw / "temp1_label").write_text("Composite", encoding="ascii")
    (hw / "temp2_input").write_text("53912", encoding="ascii")
    (hw / "temp2_label").write_text("Sensor 1", encoding="ascii")

    def fake_glob(pattern):
        if pattern.endswith("hwmon*"):
            return [str(hw)]
        return sorted(str(p) for p in hw.glob("temp*_input"))

    fake_glob_mod = SimpleNamespace(glob=fake_glob)
    monkeypatch.setattr(temperature, "glob", fake_glob_mod)
    monkeypatch.setattr(
        temperature.os.path,
        "realpath",
        lambda p: "/sys/devices/pci0/nvme/nvme1" if str(p).endswith("device") else str(p),
    )
    items = temperature._nvme_hwmon_items(str(tmp_path))
    assert [(i["key"], i["celsius"]) for i in items] == [
        ("nvme1:Composite", 56.9),
        ("nvme1:Sensor 1", 53.9),
    ]
    assert all(i["label"].startswith("nvme1") for i in items)


def test_smart_disk_temps_parse_and_skip_failed(monkeypatch):
    async def fake_run_cmd(*args, **kw):
        return (0, json.dumps({"temperature": {"current": 37}}), "") if args[-1] == "/dev/sda" else (1, "", "no")

    def fake_glob(pattern):
        return ["/dev/sda", "/dev/sdb"]

    monkeypatch.setattr(temperature, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(temperature, "glob", SimpleNamespace(glob=fake_glob))
    monkeypatch.setattr(temperature.shutil, "which", lambda x: "/usr/sbin/smartctl")
    temperature._disk_cache.update(ts=0.0, items=[])
    items = asyncio.run(temperature._smart_disk_temps())
    assert [i["label"] for i in items] == ["sda"]
    assert items[0]["zone"] == "disk"
    assert items[0]["celsius"] == 37.0


def test_smart_disk_temps_cached(monkeypatch):
    calls = []

    async def fake_run_cmd(*args, **kw):
        calls.append(args)
        return (0, json.dumps({"temperature": {"current": 40}}), "")

    monkeypatch.setattr(temperature, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(temperature, "glob", SimpleNamespace(glob=lambda p: ["/dev/sda"]))
    monkeypatch.setattr(temperature.shutil, "which", lambda x: "/usr/sbin/smartctl")
    temperature._disk_cache.update(ts=0.0, items=[])
    asyncio.run(temperature._smart_disk_temps())
    asyncio.run(temperature._smart_disk_temps())
    assert len(calls) == 1  # 60s 缓存内只探测一次
