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
    """查询历史曲线点，返回 (点列表, 主粒度)。

    粒度按窗口选：raw 保留期内用 raw，7 天内用 1m，更长用 10m。
    窗口内点数超过 points 时按时间桶平均降采样，保证任意窗口都返回铺满区间的点。
    此前实现固定取最近 N 条 raw 行，minutes 参数实际无效——24h 窗口也只覆盖最后几秒。
    窗口超过 raw 保留期时新旧两段拼接：老区段用 1m/10m（严格 < raw 起点防止与
    raw 段重叠双画），最近 raw 保留期仍用 raw——1m/10m 由 downsampler 滞后聚合，
    单查聚合表会把最近几小时漏掉。

    Args:
        db (AsyncSession): 请求作用域数据库会话。
        minutes (int): 回看窗口（分钟），截断到 MAX_MINUTES（30 天）。
        points (int): 期望点数，夹取到 [1, MAX_POINTS]。

    Returns:
        tuple[list[dict], str]: (点列表按时间升序, 主粒度)。跨粒度窗口时新旧
            两段点的 granularity 标注各自粒度。
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
    """取一个时间区段的点：点数不超上限原样返回，超了按时间桶均分降采样。

    Args:
        db (AsyncSession): 请求作用域数据库会话。
        granularity (str): 粒度（raw / 1m / 10m）。
        since (str): 起始时间（ISO 字符串，含边界）。
        span_minutes (int): 区段长度（分钟），用于计算降采样桶宽。
        points (int): 点数预算。
        until (str | None): 结束时间（ISO 字符串，不含边界）；None 表示直到当前。

    Returns:
        list[dict]: 按时间升序的点列表。
    """
    conds = [MetricPoint.granularity == granularity, MetricPoint.ts >= since]
    if until is not None:
        conds.append(MetricPoint.ts < until)
    total = await _count(db, conds)
    if total <= points:
        return await _plain(db, conds, points)
    return await _bucketed(db, conds, span_minutes, points, granularity)


def _iso_minutes_ago(minutes: int) -> str:
    """当前 UTC 时刻往前推 minutes 分钟的 ISO 时间串。

    Args:
        minutes (int): 回看分钟数。

    Returns:
        str: 与 MetricPoint.ts 存储格式一致的时间字符串（%Y-%m-%dT%H:%M:%S）。
    """
    return (datetime.now(UTC) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


async def _count(db: AsyncSession, conds: list) -> int:
    """按条件统计 MetricPoint 行数。

    Args:
        db (AsyncSession): 请求作用域数据库会话。
        conds (list): SQLAlchemy 过滤条件列表。

    Returns:
        int: 满足条件的行数。
    """
    result = await db.execute(select(func.count()).select_from(MetricPoint).where(*conds))
    return int(result.scalar_one())


async def _plain(db: AsyncSession, conds: list, limit: int) -> list[dict]:
    """按条件原样取点（点数未超预算时不降采样的路径）。

    Args:
        db (AsyncSession): 请求作用域数据库会话。
        conds (list): SQLAlchemy 过滤条件列表。
        limit (int): 最大返回点数。

    Returns:
        list[dict]: 按时间升序的点列表（取最近 limit 条后反转）。
    """
    result = await db.execute(select(MetricPoint).where(*conds).order_by(MetricPoint.ts.desc()).limit(limit))
    return [_point_dict(r) for r in list(result.scalars())[::-1]]


async def _bucketed(db: AsyncSession, conds: list, minutes: int, points: int, granularity: str) -> list[dict]:
    """窗口均分 time 桶取均值降采样（SQLite 端聚合，桶内 ts 取最早点作横坐标）。

    Args:
        db (AsyncSession): 请求作用域数据库会话。
        conds (list): SQLAlchemy 过滤条件列表。
        minutes (int): 窗口长度（分钟）。
        points (int): 目标桶数（点数）。
        granularity (str): 标注到每个输出点的粒度名。

    Returns:
        list[dict]: 按时间升序的桶均值点列表，字段含 ts / cpu_avg / cpu_max /
            mem_avg_mb / net_avg_kbps / temp_max_c / gpu_avg / disk_read_kbps /
            disk_write_kbps / granularity。
    """
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
    """按位四舍五入。

    Args:
        v (float | None): 输入值。
        digits (int): 保留小数位。

    Returns:
        float | None: 舍入结果；输入 None 时透传 None。
    """
    return None if v is None else round(v, digits)


def _point_dict(row: MetricPoint) -> dict:
    """单行记录 → 输出点 dict（字段口径契约 §2.3）。

    Args:
        row (MetricPoint): MetricPoint ORM 行（raw 或聚合粒度）。

    Returns:
        dict: 含 ts / cpu_avg / cpu_max / mem_avg_mb / net_avg_kbps /
            temp_max_c / gpu_avg / disk_read_kbps / disk_write_kbps /
            granularity；磁盘 IO 分量仅 raw 粒度有值（聚合行不采集），否则 None。
    """
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
    """区间统计（/monitor/history/stats 的服务，见契约 §3.1）。

    粒度选择与 query_history 同口径：raw 保留期内只查 raw；更长窗口老区段走
    1m/10m 聚合表、raw 尾段单独聚合，Python 端按点数加权合并（此前恒查 raw，
    长窗口既全 raw 段扫描、算出的又只是最近 raw_keep 分钟）。

    Args:
        db (AsyncSession): 请求作用域数据库会话。
        minutes (int): 回看窗口（分钟），截断到 MAX_MINUTES。
        dim (str): 统计维度（cpu/mem/temp/net/disk/gpu），未知维度按 cpu。

    Returns:
        dict: {dim, minutes, n, avg, max}；窗口内无数据时 n=0、avg/max 为 None。
    """
    minutes = min(minutes, MAX_MINUTES)
    raw_keep = max(settings.raw_keep_minutes, 1)
    column = {
        "cpu": MetricPoint.cpu,
        "mem": MetricPoint.mem_mb,
        "temp": MetricPoint.temp_max,
        "net": MetricPoint.net_kbps,
        "disk": MetricPoint.disk_read_kbps,
        "gpu": MetricPoint.gpu,
    }.get(dim, MetricPoint.cpu)

    async def _agg(granularity: str, since: str, until: str | None) -> tuple[float | None, float | None, int]:
        """聚合一个区段的 (avg, max, 行数)，until 为 None 表示直到当前。"""
        conds = [MetricPoint.granularity == granularity, MetricPoint.ts >= since]
        if until is not None:
            conds.append(MetricPoint.ts < until)
        result = await db.execute(
            select(func.avg(column), func.max(column), func.count()).where(*conds)
        )
        avg, mx, n = result.one()
        return avg, mx, int(n or 0)

    if minutes <= raw_keep:
        avg, mx, n = await _agg("raw", _iso_minutes_ago(minutes), None)
        return {"dim": dim, "minutes": minutes, "n": n, "avg": avg, "max": mx}

    granularity = "1m" if minutes <= 7 * 24 * 60 else "10m"
    raw_since = _iso_minutes_ago(raw_keep)
    older_avg, older_max, older_n = await _agg(granularity, _iso_minutes_ago(minutes), raw_since)
    raw_avg, raw_max, raw_n = await _agg("raw", raw_since, None)
    n = older_n + raw_n
    if not n:
        return {"dim": dim, "minutes": minutes, "n": 0, "avg": None, "max": None}
    pairs = [(older_avg, older_n), (raw_avg, raw_n)]
    weighted = sum((v or 0.0) * c for v, c in pairs if v is not None)
    weight = sum(c for v, c in pairs if v is not None)
    avg = weighted / weight if weight else None
    mx = max((v for v in (older_max, raw_max) if v is not None), default=None)
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
    """构建历史导出文件（契约 §3.1：/monitor/history/export 文件流）。

    Args:
        rows (list[dict]): query_history 输出的点列表。
        dim (str): 统计维度（cpu/mem/temp/net/disk/gpu），未知按 cpu_avg 字段。
        minutes (int): 回看窗口（分钟，进文件名与标题）。
        fmt (str): 导出格式（csv / markdown / html），未知格式按 html。

    Returns:
        tuple[str, str, str]: (文件名, 文件内容, media_type)。
    """
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
