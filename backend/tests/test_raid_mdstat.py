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
