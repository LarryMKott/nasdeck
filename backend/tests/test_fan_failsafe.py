"""风扇 failsafe 行为测试：传感器失联分级、临界温度、per-zone 隔离、曲线级联。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.control import FanCurve, FanZone
from app.services.control import fan_manager


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def restore_calls(monkeypatch):
    """开发机无 hwmon：拦截 restore_auto 记录调用，验证归还时机。"""
    calls = []

    def _fake(hwmon_name, pwm_channel):
        calls.append((hwmon_name, pwm_channel))
        return True

    monkeypatch.setattr(fan_manager.hwmon_driver, "restore_auto", _fake)
    return calls


def _zone(**kw) -> FanZone:
    base = dict(
        name="z",
        loop="cpu",
        hwmon_name="no_such_chip",
        pwm_channel=1,
        mode="curve",
        enabled=True,
        sensor_key="test_sensor",
    )
    base.update(kw)
    return FanZone(**base)


async def test_sensor_lost_holds_then_full_speed(db):
    curve = FanCurve(name="c", points=[[40, 30], [60, 80]], hysteresis_c=2, ramp_per_tick=50)
    db.add(curve)
    db.add(_zone(curve_id=1))
    await db.flush()

    # 前两次失联：保持现状（hold），不写 pwm
    for i in range(1, fan_manager.FAILSAFE_AFTER_TICKS):
        entry = await fan_manager._drive_zone(db, await _first_zone(db), {})
        assert entry["failsafe"] == "hold"
        assert entry["streak"] == i

    # 连续失联达到阈值：按最坏情况（过热）全速
    entry = await fan_manager._drive_zone(db, await _first_zone(db), {})
    assert entry["failsafe"] == "full_speed"
    assert entry["target_pwm_pct"] == 100.0

    # 传感器恢复：streak 清零，回到正常曲线输出
    entry = await fan_manager._drive_zone(db, await _first_zone(db), {"test_sensor": 45.0})
    assert "failsafe" not in entry
    assert entry["sensor_temp_c"] == 45.0
    assert fan_manager._sensor_fail_streak.get(1) is None


async def test_critical_temp_forces_full_speed(db):
    curve = FanCurve(name="c", points=[[40, 30], [60, 80]], hysteresis_c=2, ramp_per_tick=1)
    db.add(curve)
    db.add(_zone(curve_id=1))
    await db.flush()

    entry = await fan_manager._drive_zone(db, await _first_zone(db), {"test_sensor": 90.0})
    # 临界温度无视曲线（60C→80%）与斜率限制，直接 100%
    assert entry["target_pwm_pct"] == 100.0


async def test_apply_tick_isolates_broken_zone(db):
    # 控区 A 悬空曲线引用（模拟历史脏数据），控区 B 定速正常——A 不得拖垮 B
    db.add(_zone(name="broken", curve_id=999))
    db.add(_zone(name="ok", mode="fixed", fixed_pwm=40, sensor_key=None))
    await db.flush()

    outputs = await fan_manager.apply_tick(db)

    by_zone = {o["zone_id"]: o for o in outputs}
    assert by_zone[1]["error"] == "curve missing"
    assert by_zone[2]["target_pwm_pct"] == 40.0


async def test_release_curve_resets_referencing_zones(db, restore_calls):
    curve = FanCurve(name="c", points=[[40, 30], [60, 80]])
    db.add(curve)
    db.add(_zone(name="curve-user", curve_id=1))
    db.add(_zone(name="auto-user", mode="auto", curve_id=None))
    await db.flush()

    released = await fan_manager.release_curve(db, 1)

    assert released == [1]
    zone = (await db.execute(select(FanZone).where(FanZone.id == 1))).scalar_one()
    assert zone.mode == "auto"
    assert zone.curve_id is None
    assert restore_calls == [("no_such_chip", 1)]  # 仅受管控区归还硬件


async def test_disable_zone_restores_auto(db, restore_calls):
    db.add(_zone(name="z"))
    await db.flush()

    await fan_manager.update_zone(db, 1, {"enabled": False})

    assert restore_calls == [("no_such_chip", 1)]
    zone = (await db.execute(select(FanZone).where(FanZone.id == 1))).scalar_one()
    assert zone.enabled is False
    assert zone.mode == "curve"  # 模式保留，重新启用时仍按曲线


async def _first_zone(db):
    result = await db.execute(select(FanZone).where(FanZone.id == 1))
    return result.scalar_one()
