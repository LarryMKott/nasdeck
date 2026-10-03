"""mdstat 软 RAID 解析：卷识别 + blocks（KiB）→ size_bytes（storage/raid.py）。"""

from __future__ import annotations

from app.services.storage.raid import _mdstat_volumes

_MDSTAT = """Personalities : [raid5] [raid1]
md0 : active raid5 sdc1[2] sdb1[1] sda1[3] sdd1[0]
      8790400320 blocks super 1.2 level 5, 64k chunk, algorithm 2 [4/4] [UUUU]
      bitmap: 32/32 pages [128KB], 64KB chunk

md1 : active raid1 nvme1n1p3[0]
      865854464 blocks super 1.2 [1/1] [U]
      bitmap: 32/32 pages [128KB], 16KB chunk
"""


def test_parses_volumes_with_size(tmp_path):
    p = tmp_path / "mdstat"
    p.write_text(_MDSTAT, encoding="utf-8")
    vols = _mdstat_volumes(str(p))
    assert [v["name"] for v in vols] == ["md0", "md1"]
    assert vols[0]["size_bytes"] == 8790400320 * 1024  # blocks 单位 KiB
    assert vols[0]["level"] == "5"
    assert vols[0]["healthy"] is True
    assert vols[0]["state"] == "clean"
    assert vols[1]["size_bytes"] == 865854464 * 1024


def test_degraded_marked_unhealthy(tmp_path):
    p = tmp_path / "mdstat"
    p.write_text(
        "md0 : active raid5 sda1[0] sdb1[2](F)\n      5860267008 blocks super 1.2 level 5 [3/2] [U_U]\n",
        encoding="utf-8",
    )
    vols = _mdstat_volumes(str(p))
    assert len(vols) == 1
    assert vols[0]["healthy"] is False
    assert vols[0]["state"] == "degraded"
    assert vols[0]["size_bytes"] == 5860267008 * 1024


def test_members_structured_with_faulty_and_spare(tmp_path):
    """成员段结构化（契约 §2.8 v2.3.5）：device/index/faulty/spare，(FS) 双标记同识。"""
    p = tmp_path / "mdstat"
    p.write_text(
        "md0 : active raid5 sda1[0] sdb1[2](F) sdc1[3](S)\n"
        "      5860267008 blocks super 1.2 level 5 [4/2] [U_U_]\n",
        encoding="utf-8",
    )
    vol = _mdstat_volumes(str(p))[0]
    assert vol["members"] == [
        {"device": "sda1", "index": 0, "faulty": False, "spare": False},
        {"device": "sdb1", "index": 2, "faulty": True, "spare": False},
        {"device": "sdc1", "index": 3, "faulty": False, "spare": True},
    ]
    # 原始串保留向后兼容
    assert "sdb1[2](F)" in vol["details"]["members"]


def test_members_nvme_partition_names(tmp_path):
    p = tmp_path / "mdstat"
    p.write_text(
        "md1 : active raid1 nvme0n1p2[0] nvme1n1p2[1]\n      865854464 blocks super 1.2 [2/2] [UU]\n",
        encoding="utf-8",
    )
    vol = _mdstat_volumes(str(p))[0]
    assert [m["device"] for m in vol["members"]] == ["nvme0n1p2", "nvme1n1p2"]
    assert all(not m["faulty"] and not m["spare"] for m in vol["members"])
