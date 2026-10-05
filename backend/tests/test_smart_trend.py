"""SMART 趋势落库 + 变化速率告警回归：桶覆盖写、粒度选择、窗口增量、引擎按盘 fire。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.services.alert import engine as alert_engine
from app.services.alert.engine import evaluate_smart_rate_rules, resolve_rule_events
from app.services.storage import smart_history
from app.tasks.collectors import smart_15m
from tests.conftest import err, ok


def _now() -> datetime:
    return datetime.now(UTC).replace(minute=0, second=0, microsecond=0)


def _ata_report(device: str, attrs: dict[int, int], **extra) -> dict:
    return {
        "device": device,
        "health": "passed",
        "temp_c": 34.0,
        "power_on_hours": 3219,
        "nvme_percent_used": None,
        "nvme_media_errors": None,
        "standby": False,
        "attributes": [
            {"id": i, "name": f"attr_{i}", "value": 100, "worst": 100, "threshold": 0, "raw": str(v)}
            for i, v in attrs.items()
        ],
        **extra,
    }


def _nvme_report(device: str, percent_used: float, media_errors: int) -> dict:
    return {
        "device": device,
        "health": "passed",
        "temp_c": 41.0,
        "power_on_hours": 1200,
        "nvme_percent_used": percent_used,
        "nvme_media_errors": media_errors,
        "standby": False,
        "attributes": [],
    }


def _standby_report(device: str) -> dict:
    return {"device": device, "health": "unknown", "temp_c": None, "power_on_hours": None,
            "nvme_percent_used": None, "nvme_media_errors": None, "standby": True, "attributes": []}


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


# ---- extract_metrics ----


def test_extract_ata_whitelist_and_raw_text():
    out = smart_history.extract_metrics(_ata_report("sda", {5: 8, 197: 2, 198: 0, 177: 59, 1: 99}))
    assert out["reallocated"] == (8.0, "8")
    assert out["pending"] == (2.0, "2")
    assert out["uncorrectable"] == (0.0, "0")
    assert out["wear_leveling"] == (59.0, "59")
    assert 1 not in out  # 白名单外不采
    assert out["temp_c"] == (34.0, None)
    assert out["power_on_hours"] == (3219.0, None)


def test_extract_nvme_and_standby():
    nvme = smart_history.extract_metrics(_nvme_report("nvme0", 64.0, 3))
    assert nvme["percent_used"] == (64.0, None)
    assert nvme["media_errors"] == (3.0, None)
    assert "reallocated" not in nvme  # NVMe 无 ATA 属性表
    assert smart_history.extract_metrics(_standby_report("sda")) == {}  # 休眠盘不记录


def test_extract_raw_with_unit_suffix_takes_leading_digits():
    report = _ata_report("sda", {9: 3219})
    report["attributes"][0]["raw"] = "3219h"
    assert smart_history.extract_metrics(report)["power_on_hours"][0] == 3219.0


# ---- record / trend / rate / prune ----


async def test_record_overwrites_same_bucket(db):
    now = _now()
    assert await smart_history.record_snapshots(db, [_ata_report("sda", {5: 8})], now=now) > 0
    assert await smart_history.record_snapshots(db, [_ata_report("sda", {5: 9})], now=now) > 0
    rows = (await db.execute(select(smart_history.SmartPoint))).scalars().all()
    hour_rows = [r for r in rows if r.granularity == "1h"]
    assert len(hour_rows) == len(rows) / 2  # 同桶覆盖，无重复
    assert all(r.value == 9.0 for r in hour_rows if r.metric == "reallocated")


async def test_trend_granularity_by_days(db):
    now = _now()
    await smart_history.record_snapshots(db, [_ata_report("sda", {5: 1})], now=now)
    short = await smart_history.trend_series(db, "sda", "reallocated", days=30)
    long_ = await smart_history.trend_series(db, "sda", "reallocated", days=90)
    assert short["granularity"] == "1h" and len(short["points"]) == 1
    assert long_["granularity"] == "1d" and len(long_["points"]) == 1
    empty = await smart_history.trend_series(db, "sdb", "reallocated", days=30)
    assert empty["points"] == []


async def test_rate_deltas_window_and_new_disk(db):
    now = _now()
    await smart_history.record_snapshots(db, [_ata_report("sda", {5: 3})], now=now - timedelta(days=6))
    await smart_history.record_snapshots(db, [_ata_report("sda", {5: 5})], now=now)
    await smart_history.record_snapshots(db, [_ata_report("sdb", {5: 1})], now=now)  # 新盘仅一点
    deltas = {d["device"]: d for d in await smart_history.rate_deltas(db, "reallocated")}
    assert deltas["sda"] == {"device": "sda", "old": 3.0, "new": 5.0, "delta": 2.0}
    assert "sdb" not in deltas


async def test_prune_old(db):
    now = _now()
    await smart_history.record_snapshots(db, [_ata_report("sda", {5: 1})], now=now)
    await smart_history.record_snapshots(db, [_ata_report("sdb", {5: 1})], now=now - timedelta(days=800))
    pruned = await smart_history.prune_old(db, now=now)
    assert pruned > 0
    left = {r.device for r in (await db.execute(select(smart_history.SmartPoint))).scalars().all()}
    assert left == {"sda"}


# ---- smart_15m 采集任务 ----


async def test_smart_15m_tick_records_and_monotonic_day_marker(db, monkeypatch):
    monkeypatch.setattr(smart_15m.volume_service, "list_disks", lambda: [{"device": "sda"}])
    monkeypatch.setattr(smart_15m.smart_service, "smart_report", lambda dev: _ata_report(dev, {5: 7}))
    smart_15m._last_day = None
    await smart_15m.smart_15m_tick()
    smart_15m._last_day = None  # 幂等：重复跑不异常
    await smart_15m.smart_15m_tick()


# ---- 引擎：smart_rate 规则 ----


async def _make_rule(db, **kw) -> int:
    from app.models.alert import AlertRule

    rule = AlertRule(name="重映射扇区增长", metric=kw.get("metric", "smart_rate:reallocated"),
                     comparator=kw.get("comparator", ">="), threshold=kw.get("threshold", 1),
                     duration_ticks=1, severity="warning", channels=[], enabled=True)
    db.add(rule)
    await db.flush()
    return rule.id


async def test_smart_rate_fires_per_device_and_not_duplicated(db):
    now = _now()
    await smart_history.record_snapshots(db, [_ata_report("sda", {5: 3}), _ata_report("sdb", {5: 9})],
                                         now=now - timedelta(days=6))
    await smart_history.record_snapshots(db, [_ata_report("sda", {5: 5}), _ata_report("sdb", {5: 9})], now=now)
    rule_id = await _make_rule(db)

    fired = await evaluate_smart_rate_rules(db)
    assert len(fired) == 1  # 仅 sda 跨阈值；sdb Δ0 不触发
    assert fired[0]["metric"] == "smart_rate:reallocated"
    assert fired[0]["value"] == 2.0
    assert "sda" in fired[0]["message"]
    event_key = f"{rule_id}:sda"
    assert alert_engine._firing[event_key]

    assert await evaluate_smart_rate_rules(db) == []  # 仍 firing：不重复产生事件


async def test_smart_rate_recovers_when_delta_returns(db):
    now = _now()
    await smart_history.record_snapshots(db, [_ata_report("sda", {5: 3})], now=now - timedelta(days=6))
    await smart_history.record_snapshots(db, [_ata_report("sda", {5: 5})], now=now)
    await _make_rule(db, threshold=1)
    assert await evaluate_smart_rate_rules(db)

    # 旧点滑出 7 天窗口后 delta=0（恢复分支）——直接把旧点拨出窗口模拟时间流逝
    from sqlalchemy import delete

    await db.execute(delete(smart_history.SmartPoint).where(smart_history.SmartPoint.value == 3.0))
    await db.commit()
    fired = await evaluate_smart_rate_rules(db)
    assert len(fired) == 1 and fired[0]["status"] == "resolved"


async def test_resolve_rule_events_cleans_device_keys(db):
    now = _now()
    await smart_history.record_snapshots(db, [_ata_report("sda", {5: 3})], now=now - timedelta(days=6))
    await smart_history.record_snapshots(db, [_ata_report("sda", {5: 5})], now=now)
    rule_id = await _make_rule(db)
    await evaluate_smart_rate_rules(db)
    assert alert_engine._firing

    await resolve_rule_events(db, rule_id)
    assert alert_engine._firing == {}
    assert alert_engine._tick_counters == {}
    events = (await db.execute(select(alert_engine.AlertEvent))).scalars().all()
    assert all(e.status == "resolved" for e in events)


# ---- API：GET /storage/trend（共享测试库，盘名用独立前缀避免串扰） ----


async def test_trend_api_returns_seeded_series(client):
    from app.db.session import session_factory

    now = _now()
    async with session_factory() as db:
        await smart_history.record_snapshots(db, [_ata_report("sdtest", {5: 4})], now=now - timedelta(days=2))
        await smart_history.record_snapshots(db, [_ata_report("sdtest", {5: 6})], now=now)
        await db.commit()

    data = ok(await client.get("/api/v1/storage/trend?device=sdtest&metric=reallocated&days=30"))
    assert data["device"] == "sdtest" and data["metric"] == "reallocated"
    assert data["granularity"] == "1h" and data["days"] == 30
    values = [p["value"] for p in data["points"]]
    assert values[0] == 4.0 and values[-1] == 6.0 and values == sorted(values)

    empty = ok(await client.get("/api/v1/storage/trend?device=sdnope&metric=reallocated&days=7"))
    assert empty["points"] == []


async def test_trend_api_rejects_unknown_metric(client):
    body = err(await client.get("/api/v1/storage/trend?device=sdtest&metric=bogus"), 1001)
    assert "bogus" in body["message"] or "metric" in body["message"]
