"""Prometheus /metrics 端点回归：文本格式、缓存省略语义、无信封。"""

from __future__ import annotations

from app.api.v1.metrics import render_metrics
from app.services.monitor.cache import realtime_cache


def _seed_cache():
    realtime_cache.set("realtime", {
        "cpu_percent": 23.0, "mem_percent": 41.0, "mem_used_mb": 26200.0, "mem_total_mb": 64000.0,
        "uptime_s": 2000040, "process_count": 217, "load": [0.42, 0.38, 0.35],
        "net": {"eth0": {"rx_kbps": 12200.0, "tx_kbps": 3100.0}},
        "disk_io": {"read_kbps": 86000.0, "write_kbps": 42000.0},
    }, ttl=5)
    realtime_cache.set(
        "temperatures", [{"chip": "coretemp", "label": "Package id 0", "zone": "cpu", "celsius": 45.0}], ttl=15
    )
    realtime_cache.set("disk_health", {"sda": "passed", "sdb": "failing"}, ttl=120)
    realtime_cache.set("disk_failed", 1, ttl=120)
    realtime_cache.set("raid_degraded", 0, ttl=120)
    realtime_cache.set("gpu", {"percent": 15.0}, ttl=10)
    realtime_cache.set(
        "fan_outputs", [{"zone_id": 1, "name": "CPU_FAN", "current_rpm": 1220, "target_pwm_pct": 46.0}], ttl=10
    )


def test_render_with_seeded_cache():
    _seed_cache()
    text = render_metrics()
    assert "nasdeck_cpu_percent 23.0" in text
    assert "nasdeck_mem_percent 41.0" in text
    assert 'nasdeck_temp_celsius{chip="coretemp"' in text
    assert 'nasdeck_disk_health{device="sdb"} 2' in text  # failing=2
    assert "nasdeck_fan_rpm{zone=\"CPU_FAN\"} 1220" in text
    assert "nasdeck_net_rx_kbps 12200.0" in text
    assert "nasdeck_raid_degraded 0" in text


def test_render_omits_missing_cache():
    realtime_cache._store.clear()  # 空缓存：全部省略，只剩头两行
    text = render_metrics()
    assert "nasdeck_cpu_percent" not in text
    assert text.startswith("# HELP nasdeck_")


async def test_metrics_endpoint_raw_text(client):
    realtime_cache._store.clear()
    _seed_cache()
    resp = await client.get("/api/v1/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "nasdeck_cpu_percent" in resp.text
    assert '"code"' not in resp.text  # 无信封


