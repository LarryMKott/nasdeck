"""storcli 解析单测：夹具为按真实输出格式构造的文本（Broadcom/LSI MegaRAID）。

解析器移植自旧版 v2.3.x 实测实现；本套用例锁住关键修复行为：
VD 拓扑分隔线、JBOD 过滤、PD 行尾取型号、键值对 PD、CacheVault/双温度、容量换算。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.storage import storcli

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fake_runner(outputs: dict[str, str]):
    """按命令特征路由的 storcli 执行器桩。"""

    def run(args, timeout=30):  # noqa: ANN001
        key = " ".join(args)
        # 最长前缀优先，避免 "/c0 show copyback" 被 "/c0 show" 抢匹配
        for needle in sorted(outputs, key=len, reverse=True):
            if needle in key:
                return outputs[needle]
        return ""

    return run


@pytest.fixture(name="mega_card")
def mega_card_fixture() -> dict:
    """清 TTL 缓存后跑一轮 MegaRAID 采集。"""
    storcli._cache.update(ts=0.0, data=None)  # noqa: SLF001 测试专用复位
    runner = fake_runner(
        {
            "/c0 show all": "",  # 注意区分 eall/sall
            "/c0 show": fixture("storcli_c0_show.txt"),
            "/c0/eall/sall show all": fixture("storcli_pd_show_all.txt"),
            "/c0 /vall show": fixture("storcli_vall_show.txt"),
            "/c0 show copyback": "Auto CopyBack : Enabled",
            "temperature": "",
        }
    )
    return storcli.collect(runner)


def test_collect_mega_controller(mega_card):
    assert mega_card["ok"] is True
    assert mega_card["mode"] == "mega"
    ctrl = mega_card["controller"]
    assert ctrl["model"] == "MegaRAID 9361-8i"
    assert ctrl["serial"] == "SK55230456"
    assert ctrl["fw_version"] == "4.680.00"
    assert ctrl["roc_temp_c"] == 55
    assert ctrl["controller_temp_c"] == 48
    assert "CVPM02" in ctrl["cachevault"]
    assert ctrl["cachevault_status"] == "optimal"
    assert ctrl["auto_copyback"] == "enabled"


def test_collect_mega_drives(mega_card):
    drives = mega_card["drives"]
    # PD LIST 5 行：1 UBad + 3 Onln + 1 GHS（无 JBOD 行——JBOD 过滤在 VD 侧另有用例）
    assert len(drives) == 5
    onln = [d for d in drives if d["state"] == "Onln"]
    assert len(onln) == 3
    # 型号：行尾反向定位 + show all 键值对兜底
    assert onln[0]["model"] == "ST3600057SS"
    assert onln[0]["sn"] == "3SD2ZBW"
    assert onln[0]["brand"] == "希捷(Seagate)"
    # 温度与健康字段来自 show all 键值对
    assert onln[0]["temp_c"] == 38
    # GHS 热备识别
    hotspares = mega_card["hotspares"]
    assert len(hotspares) == 1 and hotspares[0]["hotspare"] == "global"
    assert hotspares[0]["temp_c"] == 41
    # UBad 盘 failed 判定
    ubad = [d for d in drives if d["state"] == "UBad"]
    assert ubad and ubad[0]["failed"] is True


def test_collect_mega_virtual_drives(mega_card):
    vds = mega_card["virtual_drives"]
    assert [v["type"] for v in vds] == ["RAID5", "RAID1"]
    assert vds[0]["state"] == "Optl"
    assert vds[0]["size"] == "7.276 TB"
    assert vds[0]["name"] == "data"
    # 缓存策略来自 /c0/vall show 的 Default Cache Policy
    assert "WriteBack" in vds[0]["write_policy"]
    assert vds[0]["read_policy"] == "ReadAhead"
    assert vds[1]["write_policy"] == "WriteThrough"


def test_jbod_filtered_from_topology():
    out = (
        "DG/VD TYPE  State Access Consist Cache Cac sCC  Size Name\n"
        "0/0   JBOD  Optl  RW     Yes     RWBD  -   -   3.638 TB jbod0\n"
        "0/1   RAID0 Optl  RW     Yes     RWBD  -   -   1.819 TB fast\n"
    )
    vds = storcli.parse_vds_from_topology(out)
    assert [v["name"] for v in vds] == ["fast"]


def test_size_conversions():
    # storcli TB 实为 TiB：6.366 TB → 7.0T（旧版实战值）
    assert storcli.size_to_decimal("6.366 TB") == "7.0T"
    assert storcli.size_to_decimal("3.638 TB") == "4.0T"
    assert storcli.size_to_bytes("3.638 TB") == int(3.638 * 1024**4)
    assert storcli.size_to_bytes("garbage") is None


def test_parse_pd_show_all_fields():
    pd_map = storcli.parse_pd_show_all(fixture("storcli_pd_show_all.txt"))
    rec = pd_map[("252", "4")]
    assert rec["sn"] == "3SD2ZBW"
    assert rec["model"] == "ST3600057SS"
    assert rec["temp"] == 38
    assert rec["state"] == "Onln" and rec["dg"] == "0"
    bad = pd_map[("252", "3")]
    assert bad["health"]["media_err"] == 3
    assert bad["health"]["smart_alert"] is True


def test_collect_none_when_no_output():
    storcli._cache.update(ts=0.0, data=None)  # noqa: SLF001
    card = storcli.collect(lambda args, timeout=30: "")
    assert card["ok"] is False
    assert card["mode"] == "none"
    assert card["note"]
    assert card["drives"] == []


def test_cache_ttl(mega_card):
    """TTL 内不重新执行采集（换桩后结果不变）。"""
    card2 = storcli.collect(lambda args, timeout=30: "")
    assert card2["mode"] == mega_card["mode"]


def test_brand_detection():
    assert storcli.disk_brand("ST8000NM0055") == "希捷(Seagate)"
    assert storcli.disk_brand("WD8003FFBX") == "西部数据(WD)"
    assert storcli.disk_brand("KINGSTON SA400S37") == "金士顿(Kingston)"
    assert storcli.disk_brand("SV300S37A") == ""  # 无前缀不误判（旧版 v1.7.8 修复点）


async def test_raid_status_degrades_without_storcli(monkeypatch):
    """storcli 缺失 → available=False + 错误信息，软 RAID 照常，不抛异常。"""
    from app.services.storage import raid

    async def broken_run(*_args, **_kw):
        raise RuntimeError("storcli not found")

    monkeypatch.setattr(raid, "_storcli_text_run", broken_run)
    monkeypatch.setattr(raid.storcli, "collect", lambda run: (_ for _ in ()).throw(RuntimeError("storcli not found")))
    status = await raid.raid_status()
    assert status["available"] is False
    assert status["hardware_raid"] == []
    assert "storcli" in (status["storcli_error"] or "").lower()


async def test_raid_status_contract_mapping(monkeypatch):
    """storcli 采集结果 → 契约 RaidVolumeItem/controller/drives 形状。"""
    from app.services.storage import raid

    fake_card = {
        "ok": True,
        "mode": "mega",
        "note": "",
        "controller": {"model": "MegaRAID 9361-8i", "cachevault_status": "optimal"},
        "drives": [{"slot": "252:4", "state": "Onln", "failed": False}],
        "virtual_drives": [
            {
                "dgvd": "0/0", "type": "RAID5", "state": "Optl", "name": "data",
                "size": "7.276 TB", "consist": "Yes", "cache_raw": "RWBD",
                "write_policy": "WriteBack", "read_policy": "ReadAhead", "read_cache": "Direct",
            }
        ],
        "hotspares": [],
    }
    monkeypatch.setattr(raid.storcli, "collect", lambda run: fake_card)
    status = await raid.raid_status()
    assert status["available"] is True
    assert status["controller"]["model"] == "MegaRAID 9361-8i"
    assert status["drives"][0]["slot"] == "252:4"
    vd = status["hardware_raid"][0]
    assert vd["source"] == "storcli"
    assert vd["level"] == "5"
    assert vd["healthy"] is True
    assert vd["size_bytes"] == int(7.276 * 1024**4)
    assert vd["details"]["write_policy"] == "WriteBack"


def test_detect_controllers_real_lspci():
    """真实 NAS 的 lspci 行（LSI SAS2308 HBA + Intel SATA 南桥）。"""
    out = (
        "00:17.0 SATA controller [0106]: Intel 200 Series/Z370 SATA Controller"
        " (AHCI) [8086:a282]\n"
        "02:00.0 Serial Attached SCSI controller [0107]: Broadcom / LSI SAS2308"
        " PCI-Express Fusion-MPT SAS-2 [1000:0087] (rev 05)\n"
    )
    ctls = storcli.detect_controllers(out)
    assert len(ctls) == 1  # Intel SATA 南桥不含 RAID/SAS 关键词，不误报
    assert ctls[0]["is_hba"] is True and ctls[0]["is_megaraid"] is False
    assert "SAS2308" in ctls[0]["model"]


def test_detect_controllers_megaraid():
    out = "03:00.0 RAID bus controller: LSI MegaRAID 9361-8i [1000:005d]"
    ctls = storcli.detect_controllers(out)
    assert ctls[0]["is_megaraid"] is True and ctls[0]["is_hba"] is False


def test_mdstat_real_raid5():
    """真实 NAS 的 /proc/mdstat（md0 RAID5 4/4 健康）。"""

    real = (
        "Personalities : [raid0] [raid1] [raid4] [raid5] [raid6] [raid10] [linear] \n"
        "md0 : active raid5 sdc1[2] sdb1[1] sda1[3] sdd1[0]\n"
        "      8790400320 blocks super 1.2 level 5, 64k chunk, algorithm 2 [4/4] [UUUU]\n"
        "      bitmap: 32/32 pages [128KB], 64KB chunk\n"
    )
    import unittest.mock as mock

    with mock.patch("app.services.storage.raid.read_text", return_value=real):
        vols = raid_module_volumes()
    assert len(vols) == 1
    assert vols[0]["level"] == "5" and vols[0]["healthy"] is True and vols[0]["state"] == "clean"


def raid_module_volumes():
    from app.services.storage import raid

    return raid._mdstat_volumes()


async def test_raid_status_hba_fallback(monkeypatch):
    """storcli 无 MegaRAID 可报 + lspci 有 HBA → controller 呈现 HBA、storcli_error 为说明。"""
    import unittest.mock as mock

    from app.services.storage import raid

    real_lspci = (
        "00:17.0 SATA controller [0106]: Intel 200 Series/Z370 SATA Controller (AHCI) [8086:a282]\n"
        "02:00.0 Serial Attached SCSI controller [0107]: Broadcom / LSI SAS2308"
        " PCI-Express Fusion-MPT SAS-2 [1000:0087] (rev 05)\n"
    )

    async def fake_lspci(*_a, **_kw):
        return 0, real_lspci, ""

    empty = {
        "ok": False, "mode": "none", "note": "", "controller": None,
        "drives": [], "virtual_drives": [], "hotspares": [],
    }
    with mock.patch.object(raid.storcli, "collect", lambda run: empty):
        with mock.patch.object(raid, "run_cmd", fake_lspci):
            status = await raid.raid_status()
    assert status["controller"]["mode"] == "hba"
    assert "SAS2308" in status["controller"]["model"]
    assert status["available"] is False
    assert "HBA 直通" in (status["storcli_error"] or "")


def test_list_disks_real_lsblk_shape():
    """真实 fnOS 1.2（util-linux 2.38）lsblk -Jb -o 输出片段（序列号已脱敏）。"""
    import unittest.mock as mock

    from app.services.storage import volumes

    real = (
        '{"blockdevices": ['
        '{"name":"sda","size":3000592982016,"type":"disk","rota":true,'
        '"serial":"P8XX****","model":"Hitachi HUS724030ALE641","tran":"sas",'
        '"children":[{"name":"sda1","size":3000592982016,"type":"part","rota":true}]}'
        ']}'
    )

    async def fake_run(*_a, **_kw):
        return 0, real, ""

    import asyncio

    with mock.patch.object(volumes, "run_cmd", fake_run):
        disks = asyncio.run(volumes.list_disks())
    assert len(disks) == 1
    assert disks[0]["device"] == "sda"
    assert disks[0]["size_bytes"] == 3000592982016
    assert disks[0]["transport"] == "sas"
    assert disks[0]["rotational"] is True


def test_parse_chipset_real_lspci():
    """真机 fnOS 的 lspci 行（MSI Z370 主板：ISA bridge 为芯片组，Host bridge 为平台侧）。"""
    from app.services.hardware.motherboard import parse_chipset

    real = (
        "00:00.0 Host bridge [0600]: Intel Corporation 8th Gen Core 4-core Desktop Processor"
        " Host Bridge/DRAM Registers [Coffee Lake S] [8086:3e1f] (rev 08)\n"
        "00:1f.0 ISA bridge [0601]: Intel Corporation Z370 Chipset LPC/eSPI Controller [8086:a2c9]\n"
    )
    chipset, host = parse_chipset(real)
    assert chipset == "Intel Corporation Z370 Chipset"
    assert "Coffee Lake S" in host


def test_parse_chipset_absent():
    from app.services.hardware.motherboard import parse_chipset

    chipset, host = parse_chipset("00:1f.0 Audio device [0403]: Realtek Generic [10ec:0000]")
    assert chipset is None and host is None
