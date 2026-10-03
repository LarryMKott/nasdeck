"""存储拓扑层级数据：lsblk 分区解析与缓存、storcli PD↔VD join、健康/温度回填。

对应契约 §2.5 v2.3.5（partitions）与 §2.8 v2.3.5（members）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.api.v1 import storage as storage_api
from app.services.storage import raid as raid_service
from app.services.storage import volumes as volume_service


@pytest.fixture(autouse=True)
def _clean_disks_cache():
    """list_disks 有 60s 进程内缓存：每个用例前后重置，防止污染同进程其它测试。"""
    volume_service._reset_for_test()
    yield
    volume_service._reset_for_test()

_LSBLK = json.dumps(
    {
        "blockdevices": [
            {
                "name": "sda",
                "type": "disk",
                "size": 4000787030016,
                "rota": True,
                "serial": "SN0001",
                "model": "WDC WD4003FRYZ",
                "tran": "sata",
                "children": [
                    {
                        "name": "sda1",
                        "type": "part",
                        "size": 536870912,
                        "fstype": "vfat",
                        "mountpoint": "/boot/efi",
                    },
                    {
                        "name": "sda2",
                        "type": "part",
                        "size": 3998403629056,
                        "fstype": "crypto_LUKS",
                        "mountpoint": None,
                        "children": [
                            {
                                "name": "dm-0",
                                "type": "crypt",
                                "size": 3996399894528,
                                "fstype": "btrfs",
                                "mountpoint": ["/mnt/data", "/mnt/data2"],
                            }
                        ],
                    },
                ],
            },
            {
                "name": "nvme0n1",
                "type": "disk",
                "size": 512110190592,
                "rota": False,
                "serial": "S45NNE0R",
                "model": "SAMSUNG PM9A3",
                "tran": "nvme",
                "children": [
                    {
                        "name": "nvme0n1p1",
                        "type": "part",
                        "size": 512110190592,
                        "fstype": "btrfs",
                        "mountpoint": "/",
                    }
                ],
            },
            {"name": "md126", "type": "raid1", "size": 3996399894528},
            {"name": "loop0", "type": "loop", "size": 0},
        ]
    }
)


def test_list_disks_partitions_flattened(monkeypatch):
    volume_service._reset_for_test()
    monkeypatch.setattr(volume_service, "run_cmd", _fake_run_cmd((0, _LSBLK, "")))
    disks = asyncio.run(volume_service.list_disks())
    assert [d["device"] for d in disks] == ["sda", "nvme0n1"]  # md/loop 不入清单
    parts = disks[0]["partitions"]
    assert [p["name"] for p in parts] == ["sda1", "sda2", "dm-0"]  # children 递归平铺
    assert parts[2]["type"] == "crypt"
    assert parts[2]["mountpoint"] == "/mnt/data"  # 多挂载点数组取首个
    assert parts[0]["size_bytes"] == 536870912
    assert disks[1]["partitions"][0]["mountpoint"] == "/"


def test_list_disks_cached_and_isolated(monkeypatch):
    volume_service._reset_for_test()
    calls = []
    monkeypatch.setattr(
        volume_service, "run_cmd", _fake_run_cmd_counting((0, _LSBLK, ""), calls)
    )
    first = asyncio.run(volume_service.list_disks())
    first[0]["partitions"].append({"name": "poison"})  # 调用方就地改写不得污染缓存
    second = asyncio.run(volume_service.list_disks())
    assert len(calls) == 1  # 60s 缓存内只 fork 一次
    assert all(p["name"] != "poison" for p in second[0]["partitions"])


def _fake_run_cmd(result):
    async def _run(*args, **kw):
        return result

    return _run


def _fake_run_cmd_counting(result, calls):
    async def _run(*args, **kw):
        calls.append(args)
        return result

    return _run


async def _alias_map(db):
    return {"SN0001": "数据盘"}


async def _health_map():
    return {"sda": "passed", "nvme0": "failing"}


async def _temps_map():
    return {"sda": 36.0, "nvme0": 41.5}


_STORCLI_CARD = {
    "ok": True,
    "controller": {"model": "MegaRAID 9460-16i"},
    "virtual_drives": [
        {
            "dgvd": "0/0",
            "type": "RAID5",
            "state": "Optl",
            "size": "10.937 TB",
            "name": "vol0",
        },
        {"dgvd": "1/0", "type": "RAID1", "state": "Optl", "size": "1.819 TB", "name": "vd1"},
    ],
    "drives": [
        {
            "slot": "252:0",
            "state": "Onln",
            "dg": "0",
            "size": "3.637 TB",
            "media": "HDD",
            "model": "WD4003FRYZ",
            "sn": "SN0001",
            "failed": False,
            "hotspare": None,
        },
        {
            "slot": "252:1",
            "state": "Onln",
            "dg": "0",
            "size": "3.637 TB",
            "media": "HDD",
            "model": "WD4003FRYZ",
            "sn": "SN0002",
            "failed": False,
            "hotspare": None,
        },
        {
            "slot": "252:2",
            "state": "Offln",
            "dg": "0",
            "size": "3.637 TB",
            "media": "HDD",
            "model": "WD4003FRYZ",
            "sn": "SN0003",
            "failed": True,
            "hotspare": None,
        },
        {
            "slot": "252:4",
            "state": "GHS",
            "dg": "-",
            "size": "3.637 TB",
            "media": "HDD",
            "model": "WD4003FRYZ",
            "sn": "SNHS00",
            "failed": False,
            "hotspare": "global",
        },
    ],
}


def test_raid_hardware_members_joined_by_dg(monkeypatch):
    """PD 按 DG join 进 VD members；全局热备（DG=-）不挂入任何 VD。"""
    monkeypatch.setattr(raid_service.storcli, "collect", lambda _run: _STORCLI_CARD)
    monkeypatch.setattr(raid_service, "read_text", lambda path="": "")
    status = asyncio.run(raid_service.raid_status())
    assert status["available"] is True
    vd0, vd1 = status["hardware_raid"]
    assert [m["slot"] for m in vd0["members"]] == ["252:0", "252:1", "252:2"]
    assert vd0["members"][2]["failed"] is True
    assert all(m["sn"] != "SNHS00" for m in vd0["members"])
    assert vd1["members"] == []
    assert not status["software_raid"]


def test_raid_ambiguous_dg_gets_no_members(monkeypatch):
    """DG 内多 VD 时 PD 无法唯一归属（storcli PD 表只有 DG 列），members 置空不错挂。"""
    card = {
        "ok": True,
        "controller": {"model": "MegaRAID 9460-16i"},
        "virtual_drives": [
            {"dgvd": "2/0", "type": "RAID1", "state": "Optl", "size": "1.819 TB", "name": "a"},
            {"dgvd": "2/1", "type": "RAID1", "state": "Optl", "size": "1.819 TB", "name": "b"},
        ],
        "drives": [
            {"slot": "252:0", "state": "Onln", "dg": "2", "size": "3.637 TB",
             "sn": "S1", "failed": False, "hotspare": None},
            {"slot": "252:1", "state": "Onln", "dg": "2", "size": "3.637 TB",
             "sn": "S2", "failed": False, "hotspare": None},
        ],
    }
    monkeypatch.setattr(raid_service.storcli, "collect", lambda _run: card)
    monkeypatch.setattr(raid_service, "read_text", lambda path="": "")
    status = asyncio.run(raid_service.raid_status())
    assert all(vd["members"] == [] for vd in status["hardware_raid"])


def test_disk_items_health_and_temp_backfilled(monkeypatch):
    """/storage/disks 健康与温度来自 SMART 慢采集缓存；nvme0n1 回退控制器名匹配。"""
    disks = [
        {
            "device": "sda",
            "path": "/dev/sda",
            "serial": "SN0001",
            "model": "WDC WD4003FRYZ",
            "transport": "sata",
            "size_bytes": 4000787030016,
            "size_human": "4.0 TB",
            "rotational": True,
            "partitions": [],
        },
        {
            "device": "nvme0n1",
            "path": "/dev/nvme0n1",
            "serial": "S45NNE0R",
            "model": "SAMSUNG PM9A3",
            "transport": "nvme",
            "size_bytes": 512110190592,
            "size_human": "512 GB",
            "rotational": False,
            "partitions": [],
        },
    ]
    monkeypatch.setattr(storage_api.volume_service, "list_disks", _fake_run_cmd(disks))
    monkeypatch.setattr(storage_api.disk_name, "get_alias_map", _alias_map)
    monkeypatch.setattr(storage_api.temperature, "disk_health", _health_map)
    monkeypatch.setattr(storage_api.temperature, "disk_temps", _temps_map)
    items = asyncio.run(storage_api._disk_items(None))
    assert items[0].health == "passed"
    assert items[0].temp_c == 36.0
    assert items[0].alias == "数据盘"
    assert items[1].health == "failing"  # nvme0n1 → nvme0 控制器回退
    assert items[1].temp_c == 41.5


def test_smart_key_fallback():
    assert storage_api._smart_key("sda") == "sda"
    assert storage_api._smart_key("nvme0n1") == "nvme0"
    assert storage_api._smart_key("nvme12n1") == "nvme12"
