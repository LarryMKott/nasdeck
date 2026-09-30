"""/proc/meminfo 直读与内存口径（契约 §2.1：used=Total−Available，reserved=used−buffers−cached）。"""

from __future__ import annotations

from app.services.monitor.system_resources import _mem_fields, _read_meminfo


def test_read_meminfo_parses_kb_fields(tmp_path):
    f = tmp_path / "meminfo"
    f.write_text(
        "MemTotal:       32638304 kB\n"
        "MemFree:        1234567 kB\n"
        "MemAvailable:   22662844 kB\n"
        "Buffers:          522112 kB\n"
        "Cached:         10121548 kB\n"
        "SwapTotal:       2097148 kB\n"
        "SwapFree:        2097148 kB\n"
        "HugePages_Total:       0\n",  # 无单位数值行应跳过
        encoding="ascii",
    )
    info = _read_meminfo(str(f))
    assert info["MemTotal"] == 32638304
    assert info["Cached"] == 10121548
    assert info["HugePages_Total"] == 0  # 无 kB 单位行同样解析（只查已知键，无害）


def test_read_meminfo_missing_file_returns_none(tmp_path):
    assert _read_meminfo(str(tmp_path / "nope")) is None


def test_mem_fields_reserved_negative_not_shown():
    # 用户给的示例：已使用 9.5 GiB 被缓冲+缓存（10.2 GiB）覆盖 → 系统保留负值，不展示
    fields = _mem_fields(
        {
            "MemTotal": 32638304,
            "MemAvailable": 22662844,
            "Buffers": 522112,
            "Cached": 10121548,
            "SwapTotal": 2097148,
            "SwapFree": 2097148,
        }
    )
    assert fields["total_mb"] == 31873.3
    assert fields["available_mb"] == 22131.7
    assert fields["used_mb"] == round((32638304 - 22662844) / 1024, 1)
    assert fields["buffers_mb"] == 509.9
    assert fields["cached_mb"] == 9884.3
    assert fields["reserved_mb"] is None
    assert fields["swap_percent"] == 0.0


def test_mem_fields_reserved_positive():
    # 已使用 7 GiB、缓冲 0.5 + 缓存 1.5 GiB → 系统保留 5 GiB
    fields = _mem_fields(
        {
            "MemTotal": 10 * 1024 * 1024,
            "MemAvailable": 3 * 1024 * 1024,
            "Buffers": 512 * 1024,
            "Cached": 1536 * 1024,
            "SwapTotal": 0,
            "SwapFree": 0,
        }
    )
    assert fields["used_mb"] == 7168.0
    assert fields["reserved_mb"] == 5120.0
