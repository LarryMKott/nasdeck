"""Prometheus exposition 端点（M3.6，契约 §3.7）：/api/v1/metrics 返回裸文本。

安全模型不变：服务仅绑回环，本端点不走 API Key/trim 鉴权（Prometheus 抓取端
无法携带飞牛身份头；需对外时由用户自行反代并加层）。数据全部来自实时缓存
（1s/5s/60s 采集既有产物，零额外采集 fork）；缓存缺失的指标行直接省略——
Prometheus 以 absent 语义处理，不造 0 值。
"""

from __future__ import annotations

import psutil
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.services.monitor.cache import realtime_cache

router = APIRouter(prefix="/metrics", tags=["metrics"])

_HELP_PREFIX = "# HELP nasdeck_ nasdeck exported metric\n# TYPE nasdeck_"


def _gauge(name: str, help_text: str, value: float | int | None, labels: str = "") -> str:
    """单行 gauge 指标；value 为 None（缓存缺失）返回空串（整行省略）。"""
    if value is None:
        return ""
    return f"# TYPE {name} gauge\n# HELP {name} {help_text}\n{name}{labels} {value}\n"


def render_metrics() -> str:
    """实时缓存 → exposition 文本（各段缺失即省略，不造 0 值）。"""
    snap = realtime_cache.get("realtime") or {}
    lines: list[str] = [_HELP_PREFIX]

    lines.append(_gauge("nasdeck_cpu_percent", "Host CPU usage percent", snap.get("cpu_percent")))
    lines.append(_gauge("nasdeck_mem_percent", "Memory usage percent", snap.get("mem_percent")))
    lines.append(_gauge("nasdeck_mem_used_mb", "Memory used MB", snap.get("mem_used_mb")))
    lines.append(_gauge("nasdeck_mem_total_mb", "Memory total MB", snap.get("mem_total_mb")))
    lines.append(_gauge("nasdeck_uptime_seconds", "Host uptime seconds", snap.get("uptime_s")))
    lines.append(_gauge("nasdeck_process_count", "Process count", snap.get("process_count")))

    load = snap.get("load") or []
    for i, label in ((0, "1m"), (1, "5m"), (2, "15m")):
        if i < len(load):
            lines.append(_gauge(f"nasdeck_load_{label.replace('-', '')}", f"Load {label}", load[i]))

    net = snap.get("net") or {}
    rx = sum(v.get("rx_kbps", 0) for v in net.values())
    tx = sum(v.get("tx_kbps", 0) for v in net.values())
    if net:
        lines.append(_gauge("nasdeck_net_rx_kbps", "Network receive KB/s", round(rx, 1)))
        lines.append(_gauge("nasdeck_net_tx_kbps", "Network transmit KB/s", round(tx, 1)))

    io_stats = snap.get("disk_io") or {}
    lines.append(_gauge("nasdeck_disk_read_kbps", "Disk read KB/s", io_stats.get("read_kbps")))
    lines.append(_gauge("nasdeck_disk_write_kbps", "Disk write KB/s", io_stats.get("write_kbps")))

    gpu = realtime_cache.get("gpu") or {}
    lines.append(_gauge("nasdeck_gpu_percent", "GPU usage percent", gpu.get("percent")))

    for t in realtime_cache.get("temperatures") or []:
        label = f'{{chip="{t.get("chip", "")}",label="{t.get("label", "")}",zone="{t.get("zone", "")}"}}'
        lines.append(_gauge("nasdeck_temp_celsius", "Temperature celsius", t.get("celsius"), label))

    health_map = realtime_cache.get("disk_health") or {}
    for device, health in sorted(health_map.items()):
        value = {"passed": 0, "warning": 1, "failing": 2, "unknown": 3}.get(health, 3)
        lines.append(
            _gauge("nasdeck_disk_health", "Disk health (0=passed 1=warning 2=failing 3=unknown)",
                   value, f'{{device="{device}"}}')
        )

    lines.append(_gauge("nasdeck_disk_failed", "Failing disk count", realtime_cache.get("disk_failed")))
    lines.append(_gauge("nasdeck_raid_degraded", "Degraded RAID volume count", realtime_cache.get("raid_degraded")))

    for out in realtime_cache.get("fan_outputs") or []:
        if not isinstance(out, dict) or "zone_id" not in out:
            continue
        labels = f'{{zone="{out.get("name", "")}"}}'
        lines.append(_gauge("nasdeck_fan_rpm", "Fan RPM", out.get("current_rpm"), labels))
        lines.append(_gauge("nasdeck_fan_pwm_percent", "Fan PWM percent", out.get("target_pwm_pct"), labels))

    lines.append(_gauge("nasdeck_fs_percent", "Root filesystem usage percent",
                        round(psutil.disk_usage("/").percent, 1) if snap else None))
    return "\n".join(line for line in lines if line)


@router.get("", response_class=PlainTextResponse)
async def prometheus_metrics() -> str:
    """Prometheus 抓取端点（裸 exposition 文本，无信封无鉴权，见模块 docstring）。"""
    return render_metrics()
