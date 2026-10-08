"""每盘 IO 采集单测：/proc/diskstats 整盘过滤与差分速率（花活二期 I）。"""

from __future__ import annotations

from app.services.monitor import diskstats as ds

_FAKE = (
    "   8       0 sda 100 0 1000 10 50 0 500 10 0 20 20 0 0 0\n"
    "   8       1 sda1 90 0 900 9 40 0 400 8 0 15 15 0 0 0\n"  # 分区行剔除
    "   7       0 loop0 5 0 10 1 0 0 0 0 0 1 1 0 0 0\n"  # 内存盘剔除
    " 259       0 nvme0n1 200 0 4000 20 100 0 2000 20 0 30 30 0 0 0\n"
    " 259       1 nvme0n1p1 190 0 3900 19 90 0 1900 19 0 28 28 0 0 0\n"  # 分区行剔除
    "   9       0 md0 300 0 6000 30 150 0 3000 30 0 40 40 0 0 0\n"
)


def test_read_diskstats_keeps_whole_disks_only(tmp_path):
    f = tmp_path / "diskstats"
    f.write_text(_FAKE, encoding="ascii")
    counters = ds._read_diskstats(str(f))
    assert set(counters) == {"sda", "nvme0n1", "md0"}


def test_read_diskstats_missing_file(tmp_path):
    assert ds._read_diskstats(str(tmp_path / "nope")) is None
    assert ds.snapshot(str(tmp_path / "nope")) == {}  # 非 Linux / 缺文件按无数据处理


def test_snapshot_first_sample_zero(tmp_path, monkeypatch):
    f = tmp_path / "diskstats"
    f.write_text(_FAKE, encoding="ascii")
    monkeypatch.setattr(ds, "_last", {"ts": 0.0, "counters": None})
    snap = ds.snapshot(str(f))
    assert snap["sda"]["read_iops"] == 0.0  # 首采速率为 0（与整机 disk_io 同语义）
    assert snap["md0"]["util_pct"] == 0.0


def test_snapshot_differential(tmp_path, monkeypatch):
    f = tmp_path / "diskstats"
    monkeypatch.setattr(ds, "_last", {"ts": 0.0, "counters": {"sda": (100, 50, 1000, 500, 20)}})
    monkeypatch.setattr(ds.time, "monotonic", lambda: 2.0)  # dt = 2s
    f.write_text(
        "   8       0 sda 300 0 3000 10 150 0 1500 10 0 60 40 0 0 0\n",
        encoding="ascii",
    )
    d = ds.snapshot(str(f))["sda"]
    assert d["read_iops"] == 100.0  # (300-100)/2s
    assert d["write_iops"] == 50.0
    assert d["read_kbps"] == 500.0  # 2000 扇区 ×512B / 2s / 1024
    assert d["write_kbps"] == 250.0
    assert d["util_pct"] == 2.0  # 40ms 忙 / 2000ms


def test_snapshot_new_device_and_reset_clamp(tmp_path, monkeypatch):
    """差分窗口内新出现的盘速率 0；计数回绕（重启）负差分按 0。"""
    f = tmp_path / "diskstats"
    monkeypatch.setattr(
        ds, "_last", {"ts": 0.0, "counters": {"sda": (100, 50, 1000, 500, 20), "sdb": (999, 999, 9999, 9999, 9999)}}
    )
    monkeypatch.setattr(ds.time, "monotonic", lambda: 1.0)
    f.write_text(
        "   8       0 sda 90 0 900 10 40 0 400 10 0 15 15 0 0 0\n"  # 计数回绕
        "   8      16 sdc 10 0 100 1 5 0 50 1 0 2 2 0 0 0\n",  # 新盘
        encoding="ascii",
    )
    snap = ds.snapshot(str(f))
    assert snap["sda"]["read_iops"] == 0.0 and snap["sda"]["read_kbps"] == 0.0
    assert snap["sdc"]["read_iops"] == 0.0  # 无基准速率为 0，累计量下轮起算


def test_snapshot_read_failure_keeps_baseline(tmp_path, monkeypatch):
    """瞬时读失败不更新差分基准，避免恢复后 dt 巨大把速率稀释成假低值。"""
    monkeypatch.setattr(ds, "_last", {"ts": 1.0, "counters": {"sda": (10, 5, 100, 50, 5)}})
    assert ds.snapshot(str(tmp_path / "nope")) == {}
    assert ds._last == {"ts": 1.0, "counters": {"sda": (10, 5, 100, 50, 5)}}
