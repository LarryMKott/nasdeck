"""风扇加固行为测试：温度源整体失败 failsafe（R1/T7）、PWM 写失败连击告警（R2/T3）、
关停前全量归还（T4）。针对 fan_manager 2026-10-09 评审修复的回归锁。"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.alert import AlertEvent
from app.models.control import FanCurve, FanZone
from app.services.control import fan_manager


@pytest.fixture(autouse=True)
def reset_fan_state():
    """清空模块级连击/窗口状态：各测试库 zone id 都从 1 起，不清理会互相污染。"""
    fan_manager._sensor_fail_streak.clear()
    fan_manager._write_fail_streak.clear()
    fan_manager._alert_full_until = 0.0
    fan_manager._schedule_cache.update(ts=0.0, data=None)
    yield
    fan_manager._sensor_fail_streak.clear()
    fan_manager._write_fail_streak.clear()


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


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


async def _boom_temperatures():
    """温度源整体故障：apply_tick 内 await temperatures() 抛错即触发 R1 语义。"""
    raise RuntimeError("temperature source down")


async def _empty_temperatures():
    """温度源正常但无传感器：fixed 模式不依赖温度，据此隔离 R2 用例。"""
    return []


async def _pwm_alert_count(db) -> int:
    result = await db.execute(
        select(func.count()).select_from(AlertEvent).where(AlertEvent.metric == "fan_pwm_write")
    )
    return int(result.scalar_one())


# ---------------- R1/T7：温度源整体失败 ≡ 全部传感器失联 ----------------


async def test_temperature_source_failure_treated_as_sensor_lost(db, monkeypatch):
    """温度采集整体炸掉：整轮按 failsafe 语义走（hold→full_speed），不抛异常、不冻结。"""
    monkeypatch.setattr(fan_manager, "temperatures", _boom_temperatures)
    writes = []

    def _fake_write(hwmon_name, pwm_channel, pct):
        writes.append((hwmon_name, pwm_channel, pct))
        return True

    monkeypatch.setattr(fan_manager.hwmon_driver, "write_pwm", _fake_write)

    db.add(FanCurve(name="c", points=[[40, 30], [60, 80]], hysteresis_c=2, ramp_per_tick=50))
    db.add(_zone(name="fixed", mode="fixed", fixed_pwm=40, sensor_key=None))
    db.add(_zone(name="curve", curve_id=1, pwm_channel=2))
    await db.flush()

    # 前 2 轮（未达阈值）：全部控区 hold，streak 逐轮递增，不写 pwm
    for i in range(1, fan_manager.FAILSAFE_AFTER_TICKS):
        outputs = await fan_manager.apply_tick(db)
        assert len(outputs) == 2
        for out in outputs:
            assert out["failsafe"] == "hold"
            assert out["streak"] == i
    assert writes == []

    # 第 3 轮：按最坏情况（过热）全速，且确实写到了硬件
    outputs = await fan_manager.apply_tick(db)
    for out in outputs:
        assert out["failsafe"] == "full_speed"
        assert out["target_pwm_pct"] == 100.0
    assert sorted(writes) == [("no_such_chip", 1, 100.0), ("no_such_chip", 2, 100.0)]


# ---------------- R2/T3：PWM 写失败连击 → 一次性告警事件 ----------------


async def test_write_fail_streak_alerts_once_then_resets(db, monkeypatch):
    """连续写失败第 3 拍恰落 1 条 resolved 事件（不刷屏）；写成功清零后重新计数。"""
    monkeypatch.setattr(fan_manager, "temperatures", _empty_temperatures)
    write_ok = {"ok": False}

    def _fake_write(hwmon_name, pwm_channel, pct):
        return write_ok["ok"]

    monkeypatch.setattr(fan_manager.hwmon_driver, "write_pwm", _fake_write)

    db.add(_zone(name="fixed", mode="fixed", fixed_pwm=40, sensor_key=None))
    await db.flush()

    # 第 1-2 轮：仅计数，不告警
    for _ in range(2):
        outputs = await fan_manager.apply_tick(db)
        assert len(outputs) == 1
        assert outputs[0]["error"] == "pwm write failed"
        assert "write_fail_alert" not in outputs[0]
    await db.commit()
    assert await _pwm_alert_count(db) == 0

    # 第 3 轮：恰达阈值 → output 带 write_fail_alert，同事务落 1 条 resolved 事件
    outputs = await fan_manager.apply_tick(db)
    assert "write_fail_alert" in outputs[0]
    await db.commit()
    events = (
        (await db.execute(select(AlertEvent).where(AlertEvent.metric == "fan_pwm_write"))).scalars().all()
    )
    assert len(events) == 1
    assert events[0].status == "resolved"
    assert events[0].severity == "warning"
    assert events[0].rule_name == "风扇 PWM 写入"
    assert "fixed" in events[0].message

    # 第 4 轮：持续失败不重复告警（防 5s 一条刷屏）
    outputs = await fan_manager.apply_tick(db)
    assert "write_fail_alert" not in outputs[0]
    await db.commit()
    assert await _pwm_alert_count(db) == 1

    # 写恢复成功：连击计数清零
    write_ok["ok"] = True
    outputs = await fan_manager.apply_tick(db)
    assert "error" not in outputs[0]
    await db.commit()

    # 再连续失败 3 轮：恰好再告警 1 次（成功清零计数的回归锁）
    write_ok["ok"] = False
    for _ in range(2):
        outputs = await fan_manager.apply_tick(db)
        assert "write_fail_alert" not in outputs[0]
    outputs = await fan_manager.apply_tick(db)
    assert "write_fail_alert" in outputs[0]
    await db.commit()
    assert await _pwm_alert_count(db) == 2


# ---------------- T4：关停前只归还「受管」控区 ----------------


@pytest.fixture
def restore_calls(monkeypatch):
    """开发机无 hwmon：拦截 restore_auto 记录调用，验证归还范围。"""
    calls = []

    def _fake(hwmon_name, pwm_channel):
        calls.append((hwmon_name, pwm_channel))
        return True

    monkeypatch.setattr(fan_manager.hwmon_driver, "restore_auto", _fake)
    return calls


async def test_restore_all_zones_only_enabled_managed(db, monkeypatch, restore_calls):
    """enabled 且 mode != auto 才归还；auto（内核自管）与停用控区不动。"""
    maker = async_sessionmaker(db.bind, expire_on_commit=False)
    monkeypatch.setattr(fan_manager, "session_factory", maker)  # restore_all_zones 自管会话

    async with maker() as session:
        session.add_all(
            [
                _zone(name="on-curve", pwm_channel=1),  # enabled + curve → 归还
                _zone(name="on-fixed", mode="fixed", fixed_pwm=30, sensor_key=None, pwm_channel=2),
                _zone(name="on-auto", mode="auto", sensor_key=None, pwm_channel=3),  # 不动
                _zone(name="off-curve", enabled=False, sensor_key=None, pwm_channel=4),  # 不动
            ]
        )
        await session.commit()

    await fan_manager.restore_all_zones()

    assert sorted(restore_calls) == [("no_such_chip", 1), ("no_such_chip", 2)]
