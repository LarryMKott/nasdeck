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
        dev = args[-1]
        if dev == "/dev/sda":
            return (
                0,
                json.dumps({"smart_status": {"passed": True}, "temperature": {"current": 37}}),
                "",
            )
        if dev == "/dev/nvme0":
            return (
                0,
                json.dumps({"smart_status": {"passed": True}, "temperature": {"current": 41}}),
                "",
            )
        return (1, "", "no")

    def fake_glob(pattern):
        if pattern == "/dev/sd?":
            return ["/dev/sda", "/dev/sdb"]
        if pattern == "/dev/nvme?":
            return ["/dev/nvme0"]
        return []

    monkeypatch.setattr(temperature, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(temperature, "glob", SimpleNamespace(glob=fake_glob))
    monkeypatch.setattr(temperature.shutil, "which", lambda x: "/usr/sbin/smartctl")
    # 过期戳种子（CI 新 runner 的 monotonic 可能小于 TTL，0.0 会被判「缓存新鲜」跳过扫描）
    temperature._disk_cache.update(
        ts=temperature.time.monotonic() - 1e6, items=[], health={}, temps={}
    )
    items = asyncio.run(temperature._smart_disk_temps())
    # NVMe 温度条目不上屏（hwmon 直读已覆盖 zone=nvme），只保留 SATA 盘条目
    assert [i["label"] for i in items] == ["sda"]
    assert items[0]["zone"] == "disk"
    assert items[0]["celsius"] == 37.0
    assert asyncio.run(temperature._smart_disk_temps()) == items  # 缓存命中，条目不变
    # disk_health()/disk_temps() 在非 Linux 有平台守卫，直接断言扫描产出
    assert temperature._disk_cache["health"] == {"sda": "passed", "nvme0": "passed"}
    assert temperature._disk_cache["temps"] == {"sda": 37.0, "nvme0": 41.0}


def test_smart_disk_temps_cached(monkeypatch):
    calls = []

    async def fake_run_cmd(*args, **kw):
        calls.append(args)
        return (0, json.dumps({"temperature": {"current": 40}}), "")

    def fake_glob(pattern):
        return ["/dev/sda"] if pattern == "/dev/sd?" else []

    monkeypatch.setattr(temperature, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(temperature, "glob", SimpleNamespace(glob=fake_glob))
    monkeypatch.setattr(temperature.shutil, "which", lambda x: "/usr/sbin/smartctl")
    # 过期戳种子（CI 新 runner 的 monotonic 可能小于 TTL，0.0 会被判「缓存新鲜」跳过扫描）
    temperature._disk_cache.update(
        ts=temperature.time.monotonic() - 1e6, items=[], health={}, temps={}
    )
    asyncio.run(temperature._smart_disk_temps())
    asyncio.run(temperature._smart_disk_temps())
    assert len(calls) == 1  # 60s 缓存内只探测一次
