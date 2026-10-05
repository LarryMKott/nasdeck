"""容量趋势与写满预测回归：桶覆盖写、回归斜率、days_to_full、引擎按卷 fire。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.services.alert import engine as alert_engine
from app.services.alert.engine import evaluate_capacity_rules
from app.services.storage import capacity
from app.tasks.collectors import volume_15m
from tests.conftest import ok


def _now() -> datetime:
    return datetime.now(UTC).replace(minute=0, second=0, microsecond=0)


def _vol(mount: str, used_gb: float, total_gb: float = 100.0) -> dict:
    used = int(used_gb * 1024**3)
    total = int(total_gb * 1024**3)
    return {"device": f"/dev/dm{mount}", "mount": mount, "fs_type": "btrfs",
            "total_bytes": total, "used_bytes": used, "free_bytes": total - used,
            "percent": round(used / total * 100, 1), "opts": ["rw"]}


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_engine_state():
    alert_engine._tick_counters.clear()
    alert_engine._firing.clear()
    yield
    alert_engine._tick_counters.clear()
    alert_engine._firing.clear()


async def _seed_growth(db, mount: str, per_day_gb: float, days: int = 10, start_gb: float = 30.0):
    """每 2 小时落一点模拟匀速增长。"""
    now = _now()
    points = int(days * 12)
    for i in range(points + 1):
        used = start_gb + per_day_gb * (i / 12)
        await capacity.record_snapshots(db, [_vol(mount, used)], now=now - timedelta(days=days - i / 12))


async def test_record_overwrites_and_prunes(db):
    now = _now()
    await capacity.record_snapshots(db, [_vol("/vol1", 40)], now=now - timedelta(hours=3))
    assert await capacity.record_snapshots(db, [_vol("/vol1", 41)], now=now - timedelta(hours=3)) == 1
    rows = (await db.execute(select(capacity.VolumePoint))).scalars().all()
    assert len(rows) == 1 and rows[0].used_gb == 41.0  # 同桶覆盖

    await capacity.record_snapshots(db, [_vol("/vol1", 42)], now=now - timedelta(days=200))
    assert await capacity.prune_old(db, now=now) == 1
    rows = (await db.execute(select(capacity.VolumePoint))).scalars().all()
    assert len(rows) == 1


async def test_forecast_days_to_full_on_growth(db):
    await _seed_growth(db, "/vol1", per_day_gb=1.0, days=10, start_gb=30.0)
    forecasts = {f["mount"]: f for f in await capacity.forecast_all(db)}
    f = forecasts["/vol1"]
    assert f["days_to_full"] is not None
    assert 50 < f["days_to_full"] < 80  # 已用 ~40%，日增 1% → 剩余 60 天左右
    assert 0.8 <= f["slope_percent_per_day"] <= 1.2
    assert f["last_percent"] == pytest.approx(40.0, abs=1.0)


async def test_forecast_flat_volume_returns_none(db):
    await _seed_growth(db, "/vol2", per_day_gb=0.0, days=10, start_gb=55.0)
    forecasts = await capacity.forecast_all(db)
    assert forecasts[0]["days_to_full"] is None  # 增速≈0：合法真值
    assert forecasts[0]["slope_percent_per_day"] == 0.0


async def test_forecast_skips_short_span(db):
    now = _now()
    await capacity.record_snapshots(db, [_vol("/vol3", 50)], now=now - timedelta(hours=2))
    await capacity.record_snapshots(db, [_vol("/vol3", 51)], now=now)
    forecasts = await capacity.forecast_all(db)
    assert forecasts[0]["days_to_full"] is None  # 跨度 <6h：不产预测
    assert forecasts[0]["sampled_hours"] == 2


async def test_volume_15m_tick_end_to_end(db, monkeypatch):
    monkeypatch.setattr(volume_15m.volume_service, "list_volumes", lambda: [_vol("/vol1", 42.0)])
    volume_15m._last_day = None
    await volume_15m.volume_15m_tick()
    volume_15m._last_day = None
    await volume_15m.volume_15m_tick()  # 幂等重跑不异常


async def _make_rule(db, **kw) -> int:
    from app.models.alert import AlertRule

    rule = AlertRule(name="容量即将写满", metric="capacity_forecast", comparator=kw.get("comparator", "<="),
                     threshold=kw.get("threshold", 30), duration_ticks=1, severity="warning",
                     channels=[], enabled=True)
    db.add(rule)
    await db.flush()
    return rule.id


async def test_capacity_rule_fires_and_recovers(db):
    await _seed_growth(db, "/vol1", per_day_gb=2.0, days=10, start_gb=60.0)  # 日增 2% 剩 20% → ~10 天
    await _make_rule(db, threshold=30)
    fired = await evaluate_capacity_rules(db, await capacity.forecast_all(db))
    assert len(fired) == 1 and fired[0]["value"] is not None and fired[0]["value"] <= 30
    assert "/vol1" in fired[0]["message"]

    # 增速归零（数据被清空 → forecast 缺 days_to_full）→ 恢复分支
    from sqlalchemy import delete

    await db.execute(delete(capacity.VolumePoint))
    fired = await evaluate_capacity_rules(db, [])
    assert len(fired) == 1 and fired[0]["status"] == "resolved"


# ---- API：GET /storage/volumes 的 forecast 合并（response_model 过滤回归锁） ----


async def test_volumes_api_merges_forecast(client, monkeypatch):
    from app.db.session import session_factory
    from app.services.storage import volumes as volume_service

    # 挂载点来自真实 psutil，测试注入假卷；跨度 <6h：合法真值形态（有采样无预测）
    monkeypatch.setattr(volume_service, "list_volumes", lambda: [_vol("/api-test", 52.0)])
    async with session_factory() as db:
        await capacity.record_snapshots(db, [_vol("/api-test", 50)], now=_now() - timedelta(hours=2))
        await capacity.record_snapshots(db, [_vol("/api-test", 52)], now=_now())
        await db.commit()

    volumes = ok(await client.get("/api/v1/storage/volumes"))
    assert isinstance(volumes, list) and volumes
    row = next(v for v in volumes if v["mount"] == "/api-test")
    assert "forecast" in row, "response_model 静默过滤新字段"
    assert row["forecast"]["days_to_full"] is None  # 跨度不足
    assert row["forecast"]["last_percent"] == 52.0
