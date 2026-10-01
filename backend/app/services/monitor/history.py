"""历史数据查询与降采样（契约 §2.3：raw → 1m → 10m；超 30 天不返回）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.metrics import MetricPoint

MAX_MINUTES = 30 * 24 * 60  # 30 天
MAX_POINTS = 500  # 单次返回点数上限（契约 §2.3）


async def query_history(db: AsyncSession, minutes: int, points: int) -> tuple[list[dict], str]:
    """返回 (点列表, 主粒度)。粒度按窗口选：raw 保留期内用 raw，7 天内用 1m，更长用 10m。

    窗口内点数超过 points 时按时间桶平均降采样，保证任意窗口都返回铺满区间的点。
    此前实现固定取最近 N 条 raw 行，minutes 参数实际无效——24h 窗口也只覆盖最后几秒。
    窗口超过 raw 保留期时新旧两段拼接：老区段用 1m/10m（严格 < raw 起点防止与
    raw 段重叠双画），最近 raw 保留期仍用 raw——1m/10m 由 downsampler 滞后聚合，
    单查聚合表会把最近几小时漏掉。
    """
    minutes = min(minutes, MAX_MINUTES)
    points = max(1, min(points, MAX_POINTS))
    raw_keep = max(settings.raw_keep_minutes, 1)
    if minutes <= raw_keep:
        return await _window(db, "raw", _iso_minutes_ago(minutes), minutes, points), "raw"
    granularity = "1m" if minutes <= 7 * 24 * 60 else "10m"
    raw_since = _iso_minutes_ago(raw_keep)
    older_span = minutes - raw_keep
    older_points = max(1, round(points * older_span / minutes))
    rows = await _window(db, granularity, _iso_minutes_ago(minutes), older_span, older_points, until=raw_since)
    rows += await _window(db, "raw", raw_since, raw_keep, max(1, points - older_points))
    return rows, granularity


async def _window(
    db: AsyncSession,
    granularity: str,
    since: str,
    span_minutes: int,
    points: int,
    until: str | None = None,
) -> list[dict]:
    """取一个区段的点：点数不超上限原样返回，超了按时间桶均分降采样。"""
    conds = [MetricPoint.granularity == granularity, MetricPoint.ts >= since]
    if until is not None:
        conds.append(MetricPoint.ts < until)
    total = await _count(db, conds)
    if total <= points:
        return await _plain(db, conds, points)
    return await _bucketed(db, conds, span_minutes, points, granularity)


def _iso_minutes_ago(minutes: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


async def _count(db: AsyncSession, conds: list) -> int:
    result = await db.execute(select(func.count()).select_from(MetricPoint).where(*conds))
    return int(result.scalar_one())


async def _plain(db: AsyncSession, conds: list, limit: int) -> list[dict]:
    result = await db.execute(select(MetricPoint).where(*conds).order_by(MetricPoint.ts.desc()).limit(limit))
    return [_point_dict(r) for r in list(result.scalars())[::-1]]


async def _bucketed(db: AsyncSession, conds: list, minutes: int, points: int, granularity: str) -> list[dict]:
    """窗口均分 time 桶取均值：SQLite 端聚合，桶内 ts 取最早点作横坐标。"""
    bucket_seconds = max(ceil(minutes * 60 / points), 1)
    bucket = cast(func.strftime("%s", MetricPoint.ts) / bucket_seconds, Integer)
    result = await db.execute(
        select(
            func.min(MetricPoint.ts),
            func.avg(MetricPoint.cpu),
            func.max(MetricPoint.cpu),
            func.avg(MetricPoint.mem_mb),
            func.avg(MetricPoint.net_kbps),
            func.max(MetricPoint.temp_max),
            func.avg(MetricPoint.gpu),
            func.avg(MetricPoint.disk_read_kbps),
            func.avg(MetricPoint.disk_write_kbps),
        )
        .where(*conds)
        .group_by(bucket)
        .order_by(func.min(MetricPoint.ts))
    )
    rows = result.all()
    out = []
    for r in rows:
        out.append(
            {
                "ts": r[0],
                "cpu_avg": _round(r[1], 2),
                "cpu_max": _round(r[2], 2),
                "mem_avg_mb": _round(r[3], 1),
                "net_avg_kbps": _round(r[4], 1),
                "temp_max_c": r[5],
                "gpu_avg": _round(r[6], 2),
                "disk_read_kbps": _round(r[7], 1),
                "disk_write_kbps": _round(r[8], 1),
                "granularity": granularity,
            }
        )
    return out


def _round(v: float | None, digits: int) -> float | None:
    return None if v is None else round(v, digits)


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
    """区间统计（/monitor/history/stats 的服务，见契约 §3.1）。"""
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
        select(func.avg(column), func.max(column), func.count()).where(
            MetricPoint.granularity == "raw", MetricPoint.ts >= since
        )
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
    """构建导出文件（契约 §3.1：/monitor/history/export 文件流）。返回 (文件名, 内容, media_type)。"""
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
        head += f"- 采样点：{len(rows)}\n- 均值：{avg:.1f}{unit}\n- 峰值：{max(stats, default=0):.1f}{unit}\n\n"
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
