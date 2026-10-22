"""硬盘健康预言（花活二期 J）：smart_points 1h 桶斜率 → 0-100 健康分 + 五维雷达 + 触阈值 ETA。

评分口径：变化速率为主、绝对值为辅；无历史的新盘只按当前值给分（当前值来自
smart_15m 喂入的报告缓存）。ETA 只在拿得到阈值时给出：ATA 取 smartctl THRESH
列（smart_15m 缓存），NVMe 用 percent_used 剩余寿命外推；拿不到即不出——
"无阈值"是合法真值，前端显"—"。最小二乘先例同 capacity.py。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage import SmartPoint
from app.services.storage.smart_history import TRACKED_METRICS, extract_metrics

# 回归窗口（1h 桶）与采样门槛：≥3 点且跨度 ≥6h 才回归（先例 capacity._MIN_SPAN_HOURS）
WINDOW_DAYS = 14
_MIN_POINTS = 3
_MIN_SPAN_HOURS = 6

# 五维权重（缺失维度剔除后权重重归一）
_DIM_WEIGHTS = {"reallocated": 0.30, "pending": 0.20, "media": 0.20, "temp": 0.15, "wear": 0.15}
DIM_KEYS = tuple(_DIM_WEIGHTS)

# 增长类维度扣分：日增速 × 系数（0.25/天 扣满）+ 非零绝对值小额扣分
_RATE_K = 400.0
_NONZERO_PENALTY = 5.0

# 温度余量：近期均温距 60 °C 的余量折算（余量 ≥25 °C 满分）
_TEMP_HOT = 60.0
_TEMP_SPAN = 25.0

# 磨损：NVMe percent_used 直读；ATA 以通电时长代理（6 年线性耗尽，仅缺磨损属性时）
_WEAR_HOURS_FULL = 6 * 365 * 24

# THRESH / 最新指标缓存（smart_15m 每轮喂入；重启后 15 分钟内自愈）
_thresh: dict[str, dict[str, float]] = {}
_latest: dict[str, dict[str, float]] = {}

# ATA 属性 id → 指标名（与 smart_history._ATA_METRICS 同源）
_THRESH_METRICS = {5: "reallocated", 197: "pending", 198: "uncorrectable"}


def reset_for_test() -> None:
    """清空阈值/最新值缓存（测试隔离）。"""
    _thresh.clear()
    _latest.clear()


def remember_reports(reports: list[dict]) -> None:
    """smart_15m 采样后喂入报告：缓存 ATA THRESH 列与最新指标值。

    Args:
        reports (list[dict]): smart_report 列表（attributes 含 threshold 字段）。
    """
    for report in reports:
        device = report.get("device")
        if not device:
            continue
        thresh: dict[str, float] = {}
        for attr in report.get("attributes") or []:
            metric = _THRESH_METRICS.get(attr.get("id"))
            th = attr.get("threshold")
            if metric and th:
                thresh[metric] = float(th)
        if thresh:
            _thresh[device] = thresh
        _latest[device] = {k: v[0] for k, v in extract_metrics(report).items()}


def _slope_per_day(points: list[tuple[datetime, float]]) -> float | None:
    """最小二乘斜率（单位/天）；跨度不足或时间方差为 0 返回 None。"""
    t0 = points[0][0]
    xs = [(dt - t0).total_seconds() / 86400 for dt, _ in points]
    ys = [v for _, v in points]
    if xs[-1] < _MIN_SPAN_HOURS / 24:
        return None
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx


def _growth_dim(current: float | None, rate: float | None) -> float | None:
    """坏扇区类维度（重映射/待定/介质错误）：速率扣分为主，非零绝对值小额扣分。"""
    if current is None:
        return None
    dim = 100.0
    if current > 0:
        dim -= _NONZERO_PENALTY
    if rate is not None and rate > 0:
        dim -= min(100.0, rate * _RATE_K)
    return max(0.0, dim)


def _temp_dim(avg_temp: float | None) -> float | None:
    """温度余量维度：余量 ≥25 °C 满分，触及 60 °C 归零。"""
    if avg_temp is None:
        return None
    return max(0.0, min(100.0, (_TEMP_HOT - avg_temp) / _TEMP_SPAN * 100))


def _wear_dim(latest: dict[str, float]) -> float | None:
    """磨损维度：NVMe percent_used 直读；ATA 用通电时长代理。"""
    if latest.get("percent_used") is not None:
        return max(0.0, 100.0 - float(latest["percent_used"]))
    hours = latest.get("power_on_hours")
    if hours:
        return max(0.0, 100.0 - float(hours) / _WEAR_HOURS_FULL * 100)
    return None


def _etas(device: str, latest: dict[str, float], rates: dict[str, float]) -> list[dict]:
    """触阈值倒计时：ATA 取 THRESH 外推，NVMe percent_used 外推到 100。

    只在「拿得到阈值 + 有正增速 + 尚未触顶」时给出；否则为空（前端显"—"）。
    """
    out: list[dict] = []
    thresh = _thresh.get(device, {})
    for metric in ("reallocated", "pending", "uncorrectable"):
        threshold = thresh.get(metric)
        cur = latest.get(metric)
        rate = rates.get(metric)
        if threshold is None or cur is None or rate is None or rate <= 0 or cur >= threshold:
            continue
        out.append(
            {
                "metric": metric,
                "days": round((threshold - cur) / rate, 1),
                "current": cur,
                "threshold": threshold,
                "slope_per_day": round(rate, 4),
            }
        )
    pu_cur, pu_rate = latest.get("percent_used"), rates.get("percent_used")
    if pu_cur is not None and pu_rate is not None and pu_rate > 0 and pu_cur < 100:
        out.append(
            {
                "metric": "percent_used",
                "days": round((100 - pu_cur) / pu_rate, 1),
                "current": pu_cur,
                "threshold": 100.0,
                "slope_per_day": round(pu_rate, 4),
            }
        )
    return out


def _oracle_for(device: str, metrics: dict[str, list[tuple[datetime, float]]]) -> dict:
    """单盘预言装配：斜率 → 五维 → 加权分 → ETA。"""
    latest_hist = {m: pts[-1][1] for m, pts in metrics.items()}
    # 历史缺失的指标用报告缓存补（新盘/休眠盘只按当前值给分）
    latest = {**_latest.get(device, {}), **latest_hist}
    rates = {}
    for m, pts in metrics.items():
        if len(pts) >= _MIN_POINTS:
            s = _slope_per_day(pts)
            if s is not None:
                rates[m] = s

    temp_now = latest.get("temp_c")
    temp_pts = metrics.get("temp_c") or []
    if temp_pts:
        recent = [v for dt, v in temp_pts if (temp_pts[-1][0] - dt).total_seconds() <= 86400]
        if recent:
            temp_now = sum(recent) / len(recent)

    media_cur = latest.get("media_errors")
    if media_cur is None:
        media_cur = latest.get("uncorrectable")
    media_rate = rates.get("media_errors")
    if media_rate is None:
        media_rate = rates.get("uncorrectable")

    dims = {
        "reallocated": _growth_dim(latest.get("reallocated"), rates.get("reallocated")),
        "pending": _growth_dim(latest.get("pending"), rates.get("pending")),
        "media": _growth_dim(media_cur, media_rate),
        "temp": _temp_dim(temp_now),
        "wear": _wear_dim(latest),
    }
    known = {k: v for k, v in dims.items() if v is not None}
    total_w = sum(_DIM_WEIGHTS[k] for k in known)
    score = round(sum(v * _DIM_WEIGHTS[k] for k, v in known.items()) / total_w) if total_w else None
    grade = None if score is None else ("good" if score >= 85 else "watch" if score >= 60 else "bad")
    return {
        "score": score,
        "grade": grade,
        "has_history": bool(metrics),
        "dims": [{"key": k, "value": dims[k]} for k in DIM_KEYS],
        "etas": _etas(device, latest, rates),
    }


async def forecast_all(db: AsyncSession, devices: list[str], now: datetime | None = None) -> dict[str, dict]:
    """批量计算各盘预言（/storage/disks 单次装配，一查不逐盘）。

    Args:
        db (AsyncSession): 只读会话。
        devices (list[str]): SMART 探测键列表（smart_key 归一后）。
        now (datetime | None): 回归窗口基准时刻；None 取当前 UTC。

    Returns:
        dict[str, dict]: 探测键 → {score, grade, has_history, dims, etas}。
    """
    devices = [d for d in dict.fromkeys(devices) if d]
    if not devices:
        return {}
    series: dict[str, dict[str, list[tuple[datetime, float]]]] = {}
    if db is not None:
        now = now or datetime.now(UTC)
        since = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
        result = await db.execute(
            select(SmartPoint.device, SmartPoint.ts, SmartPoint.metric, SmartPoint.value)
            .where(
                SmartPoint.granularity == "1h",
                SmartPoint.metric.in_(TRACKED_METRICS),
                SmartPoint.device.in_(devices),
                SmartPoint.ts >= since,
            )
            .order_by(SmartPoint.device, SmartPoint.metric, SmartPoint.ts)
        )
        for device, ts, metric, value in result.all():
            try:
                dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
            except ValueError:
                continue
            series.setdefault(device, {}).setdefault(metric, []).append((dt, value))
    return {device: _oracle_for(device, series.get(device, {})) for device in devices}
