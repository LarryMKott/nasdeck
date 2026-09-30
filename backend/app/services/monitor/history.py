"""历史数据查询与降采样（契约 §2.3：raw → 1m → 10m；超 30 天不返回）。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metrics import MetricPoint

MAX_MINUTES = 30 * 24 * 60  # 30 天


async def query_history(
    db: AsyncSession, minutes: int, points: int
) -> tuple[list[dict], str]:
    """返回 (点列表, 主粒度)。窗口全在 raw 保留期内用 raw，否则 1m；10m 留给更长窗口。"""
    minutes = min(minutes, MAX_MINUTES)
    granularity = "raw"
    rows: list[MetricPoint] = []
    # raw 窗口：直接取最近 minutes 分钟
    result = await db.execute(
        select(MetricPoint)
        .where(MetricPoint.granularity == "raw")
        .order_by(MetricPoint.ts.desc())
        .limit(min(points, 500))
    )
    rows = list(result.scalars())[::-1]
    if rows:
        span_minutes = _span_minutes(rows[0].ts, rows[-1].ts)
        if span_minutes > minutes + 5:
            granularity = "1m"
            result = await db.execute(
                select(MetricPoint)
                .where(MetricPoint.granularity == "1m")
                .order_by(MetricPoint.ts.desc())
                .limit(min(points, 500))
            )
            rows = list(result.scalars())[::-1]
    return [_point_dict(r) for r in rows], granularity


def _span_minutes(ts_start: str, ts_end: str) -> float:
    from datetime import datetime

    fmt = "%Y-%m-%dT%H:%M:%S"
    try:
        a = datetime.strptime(ts_start, fmt)
        b = datetime.strptime(ts_end, fmt)
        return (b - a).total_seconds() / 60
    except ValueError:
        return 0.0


def _point_dict(row: MetricPoint) -> dict:
    return {
        "ts": row.ts,
        "cpu_avg": row.cpu,
        "cpu_max": row.cpu,
        "mem_avg_mb": row.mem_mb,
        "net_avg_kbps": row.net_kbps,
        "temp_max_c": row.temp_max,
        "gpu_avg": row.gpu,
        "disk_read_kbps": row.disk_read_kbps if row.granularity == "raw" else None,
        "disk_write_kbps": row.disk_write_kbps if row.granularity == "raw" else None,
        "granularity": row.granularity,
    }


async def stats(db: AsyncSession, minutes: int, dim: str) -> dict:
    """区间统计（规划接口 /monitor/history/stats 的服务，见契约 §6.1）。"""
    from datetime import UTC, datetime, timedelta

    since = (datetime.now(UTC) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")
    column = {
        "cpu": MetricPoint.cpu,
        "mem": MetricPoint.mem_mb,
        "temp": MetricPoint.temp_max,
        "net": MetricPoint.net_kbps,
        "disk": MetricPoint.disk_read_kbps,
        "gpu": MetricPoint.gpu,
    }.get(dim, MetricPoint.cpu)
    result = await db.execute(
        select(func.avg(column), func.max(column), func.count())
        .where(MetricPoint.granularity == "raw", MetricPoint.ts >= since)
    )
    avg, mx, n = result.one()
    return {"dim": dim, "minutes": minutes, "n": n, "avg": avg, "max": mx}


_DIM_FIELDS = {
    "cpu": "cpu_avg",
    "mem": "mem_avg_mb",
    "temp": "temp_max_c",
    "net": "net_avg_kbps",
    "disk": "disk_read_kbps",
    "gpu": "gpu_avg",
}


def export_build(rows: list[dict], dim: str, minutes: int, fmt: str) -> tuple[str, str, str]:
    """构建导出文件（契约 §6.1：/monitor/history/export 文件流）。返回 (文件名, 内容, media_type)。"""
    from datetime import UTC, datetime

    unit = {"cpu": "%", "mem": "MB", "temp": "C", "net": "KB/s", "disk": "KB/s", "gpu": "%"}.get(dim, "")
    field = _DIM_FIELDS.get(dim, "cpu_avg")
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    label = {"cpu": "CPU", "mem": "内存", "temp": "温度", "net": "网络", "disk": "磁盘IO", "gpu": "GPU"}.get(dim, dim)
    values = [r.get(field) for r in rows]
    if fmt == "csv":
        lines = ["ts,value"] + [f"{r['ts']},{'' if v is None else v}" for r, v in zip(rows, values, strict=False)]
        return f"history_{dim}_{minutes}m_{ts}.csv", "\n".join(lines), "text/csv"
    if fmt == "markdown":
        head = f"# nasdeck 历史健康报告 · {label} · 最近 {minutes} 分钟\n\n"
        stats = [v for v in values if v is not None]
        avg = sum(stats) / len(stats) if stats else 0
        head += (
            f"- 采样点：{len(rows)}\n- 均值：{avg:.1f}{unit}\n- 峰值：{max(stats, default=0):.1f}{unit}\n\n"
        )
        head += "| 时间 | 数值 |\n|---|---|\n"
        head += "\n".join(
            f"| {r['ts']} | {'' if v is None else f'{v}{unit}'} |" for r, v in zip(rows, values, strict=False)
        )
        return f"history_{dim}_{minutes}m_{ts}.md", head, "text/markdown"
    body = "".join(
        f"<tr><td>{r['ts']}</td><td>{'' if v is None else f'{v}{unit}'}</td></tr>"
        for r, v in zip(rows, values, strict=False)
    )
    html = (
        f"<!DOCTYPE html><html lang=zh-CN><meta charset=utf-8><title>nasdeck 历史报告 · {label}</title>"
        f"<h1>nasdeck 历史健康报告 · {label} · 最近 {minutes} 分钟</h1>"
        f"<table border=1 cellpadding=4><tr><th>时间</th><th>数值</th></tr>{body}</table>"
    )
    return f"history_{dim}_{minutes}m_{ts}.html", html, "text/html"
