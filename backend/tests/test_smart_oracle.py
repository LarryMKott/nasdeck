"""硬盘健康预言单测：斜率、五维评分、THRESH 外推 ETA 与 API 字段（花活二期 J）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.services.storage import smart_history, smart_oracle
from tests.conftest import ok


def _now() -> datetime:
    return datetime.now(UTC).replace(minute=0, second=0, microsecond=0)


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
def _reset_oracle():
    smart_oracle.reset_for_test()
    yield
    smart_oracle.reset_for_test()


def test_slope_per_day_and_short_span():
    t0 = _now()
    pts = [(t0 + timedelta(hours=i), float(i)) for i in range(0, 49, 12)]  # 2 天 12h，24h/天
    assert smart_oracle._slope_per_day(pts) == pytest.approx(24.0)
    short = [(t0 + timedelta(hours=i), float(i)) for i in range(3)]  # 跨度 2h：噪声不回归
    assert smart_oracle._slope_per_day(short) is None


def test_growth_dim_rate_primary_absolute_secondary():
    assert smart_oracle._growth_dim(None, None) is None  # 无数据
    assert smart_oracle._growth_dim(0.0, 0.0) == 100.0  # 干净且零增速
    assert smart_oracle._growth_dim(3.0, 0.0) == 95.0  # 非零但稳定：小额扣分
    # 日增 0.1：100 - 0.1*400 - 5 = 55
    assert smart_oracle._growth_dim(3.0, 0.1) == 55.0
    assert smart_oracle._growth_dim(1.0, 1.0) == 0.0  # 快速恶化钳 0


def test_temp_and_wear_dims():
    assert smart_oracle._temp_dim(None) is None
    assert smart_oracle._temp_dim(35.0) == 100.0  # 余量 ≥25 满分
    assert smart_oracle._temp_dim(60.0) == 0.0  # 触线归零
    assert smart_oracle._wear_dim({"percent_used": 30.0}) == 70.0  # NVMe 直读
    assert smart_oracle._wear_dim({"power_on_hours": 26280}) == 50.0  # 3 年 → 半分
    assert smart_oracle._wear_dim({}) is None


def test_remember_reports_and_etas():
    smart_oracle.remember_reports(
        [
            {
                "device": "sda",
                "attributes": [
                    {"id": 5, "raw": "8", "threshold": 10},
                    {"id": 197, "raw": "0", "threshold": 0},
                ],
                "temp_c": 36.0,
                "power_on_hours": 10000,
            }
        ]
    )
    assert smart_oracle._thresh["sda"] == {"reallocated": 10.0}
    assert smart_oracle._latest["sda"]["power_on_hours"] == 10000.0
    # 当前 8、日增 0.1 → 触阈值 10 还剩 20 天
    etas = smart_oracle._etas("sda", {"reallocated": 8.0}, {"reallocated": 0.1})
    assert etas == [
        {"metric": "reallocated", "days": 20.0, "current": 8.0, "threshold": 10.0, "slope_per_day": 0.1}
    ]
    # 无阈值 / 无增速 / 已触顶 均不产出（合法真值）
    assert smart_oracle._etas("sda", {"pending": 5.0}, {"pending": 0.5}) == []
    assert smart_oracle._etas("sda", {"reallocated": 12.0}, {"reallocated": 0.1}) == []
    assert smart_oracle._etas("sda", {"reallocated": 8.0}, {"reallocated": 0.0}) == []


async def test_forecast_all_history_and_new_disk(db):
    now = _now()
    # sda：重映射 10 天涨 2（0.2/天，超 _MIN_POINTS 且跨度足）；温度 36 稳定
    for i in range(0, 11):
        ts = (now - timedelta(days=10 - i)).strftime("%Y-%m-%dT%H:%M:%S")
        db.add_all(
            [
                smart_history.SmartPoint(
                    ts=ts, granularity="1h", device="sda", metric="reallocated", value=2.0 + 0.2 * i
                ),
                smart_history.SmartPoint(
                    ts=ts, granularity="1h", device="sda", metric="temp_c", value=36.0
                ),
            ]
        )
    await db.commit()
    smart_oracle.remember_reports([{"device": "sdb", "temp_c": 40.0, "power_on_hours": 26280}])

    out = await smart_oracle.forecast_all(db, ["sda", "sdb"])
    sda = out["sda"]
    assert sda["has_history"] is True
    assert sda["score"] is not None and sda["score"] < 100  # 增速扣分生效
    assert sda["grade"] in ("good", "watch", "bad")
    dim_map = {d["key"]: d["value"] for d in sda["dims"]}
    assert dim_map["reallocated"] == 15.0  # 100 - 0.2*400 - 5
    assert dim_map["temp"] == 96.0  # 均温 36 → 余量 24/25
    # sdb：无历史新盘，只按当前值给分（磨损 6 年折半 + 温度余量 20/25）
    sdb = out["sdb"]
    assert sdb["has_history"] is False
    assert sdb["score"] is not None
    sdb_dims = {d["key"]: d["value"] for d in sdb["dims"]}
    assert sdb_dims["wear"] == 50.0 and sdb_dims["temp"] == 80.0


async def test_disks_api_includes_oracle(client, db, monkeypatch):
    """response_model 静默过滤回归锁：/storage/disks 必须透出 oracle 字段。"""
    from app.db.session import session_factory
    from app.services.storage import volumes as volume_service

    async def _fake_disks():
        return [
            {
                "device": "sdz",
                "path": "/dev/sdz",
                "size_bytes": 4 * 1024**4,
                "size_human": "4 TB",
                "rotational": True,
            }
        ]

    monkeypatch.setattr(volume_service, "list_disks", _fake_disks)
    now = _now()
    async with session_factory() as dbw:
        for i in range(0, 9):
            dbw.add(
                smart_history.SmartPoint(
                    ts=(now - timedelta(days=8 - i)).strftime("%Y-%m-%dT%H:%M:%S"),
                    granularity="1h",
                    device="sdz",
                    metric="pending",
                    value=float(i),
                )
            )
        await dbw.commit()

    disks = ok(await client.get("/api/v1/storage/disks"))
    row = next(d for d in disks if d["device"] == "sdz")
    assert "oracle" in row, "response_model 静默过滤新字段"
    assert row["oracle"]["has_history"] is True
    assert row["oracle"]["score"] is not None
