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


# ------------------------------------------------------------ 2026-10-25 PR4 补锁


async def test_curve_missing_goes_failsafe_not_freeze(db):
    """悬空曲线引用与传感器失联同级：hold → full_speed，PWM 不得静默冻结（P1-4）。"""
    db.add(_zone(curve_id=999))
    await db.flush()

    for i in range(1, fan_manager.FAILSAFE_AFTER_TICKS):
        entry = await fan_manager._drive_zone(db, await _first_zone(db), {})
        assert entry["failsafe"] == "hold" and entry["error"] == "curve missing"

    entry = await fan_manager._drive_zone(db, await _first_zone(db), {})
    assert entry["failsafe"] == "full_speed" and entry["target_pwm_pct"] == 100.0


async def test_fixed_mode_critical_temp_forces_full_speed(db):
    """fixed 模式同样受临界温度保护：85℃ 低温占空比不再照跑（旧 P1-03）。"""
    db.add(_zone(mode="fixed", fixed_pwm=20, sensor_key=None))
    await db.flush()

    entry = await fan_manager._drive_zone(db, await _first_zone(db), {}, cpu_default=91.0)
    assert entry["target_pwm_pct"] == 100.0 and entry["sensor_temp_c"] == 91.0
    # 温度正常时保持定速
    entry = await fan_manager._drive_zone(db, await _first_zone(db), {}, cpu_default=45.0)
    assert entry["target_pwm_pct"] == 20.0


async def test_sensor_fallback_uses_cpu_zone_max(db):
    """无显式 sensor_key 时回退取 cpu zone 最高温（旧 P1-04：曾任意取第一项，
    ARM 机器上 CPU 风扇会跟第一块盘的 30℃ 走）。"""
    curve = FanCurve(name="c", points=[[40, 30], [60, 80]])
    db.add(curve)
    db.add(_zone(curve_id=1, sensor_key=None))
    await db.flush()

    temps = {"smart:sda": 30.0, "smart:nvme0": 33.0}
    items = [
        {"key": "smart:sda", "celsius": 30.0, "zone": "disk"},
        {"key": "thermal:cpu_thermal", "celsius": 62.0, "zone": "cpu"},
        {"key": "hwmon:coretemp1", "celsius": 58.0, "zone": "cpu"},
    ]
    # 温度 dict 按旧回退（任取第一项）会得到 30 → 30% 占空比；正确回退取 cpu max 62 → 高档
    cpu_default = max((t["celsius"] for t in items if t["zone"] == "cpu"), default=None)
    assert cpu_default == 62.0
    entry = await fan_manager._drive_zone(db, await _first_zone(db), temps, cpu_default)
    assert entry["sensor_temp_c"] == 62.0
    assert entry["target_pwm_pct"] > 30.0  # 曲线按 62℃ 输出，远高于按盘温 30℃ 的结果
    # 完全没有 cpu zone 传感器：按失联走 failsafe，而不是拿盘温当 cpu 温
    entry = await fan_manager._drive_zone(db, await _first_zone(db), temps, None)
    assert entry.get("failsafe") == "hold"


async def test_apply_tick_survives_temperature_exception(db, monkeypatch):
    """采集函数抛异常不再让整轮调速消失：空温度推进 failsafe streak（P1-02）。"""
    curve = FanCurve(name="c", points=[[40, 30], [60, 80]])
    db.add(curve)
    db.add(_zone(curve_id=1))
    await db.flush()

    async def _boom():
        raise RuntimeError("psutil explode")

    monkeypatch.setattr(fan_manager, "temperatures", _boom)
    for _ in range(fan_manager.FAILSAFE_AFTER_TICKS):
        outputs = await fan_manager.apply_tick(db)
    assert outputs[0]["failsafe"] == "full_speed"


async def test_restore_auto_failure_is_logged_and_surfaced(db, monkeypatch, caplog):
    """交还内核失败必须留痕并在响应体可见（P1-5：曾 4 处调用全忽略返回值）。"""
    db.add(_zone(name="z"))
    await db.flush()

    def _fail(hwmon_name, pwm_channel):
        return False

    monkeypatch.setattr(fan_manager.hwmon_driver, "restore_auto", _fail)
    with caplog.at_level("WARNING"):
        result = await fan_manager.update_zone(db, 1, {"enabled": False})
    assert result["warning"] and "restore_auto" in result["warning"]
    assert any("交还内核" in r.message for r in caplog.records)


async def test_create_zone_rejects_readonly_channel(db, monkeypatch):
    """chip 在位但通道只读：创建受管控区直接拒绝（N4 闭环）。"""
    monkeypatch.setattr(
        fan_manager.hwmon_driver,
        "scan_channels",
        lambda: [{"chip": "fan0", "pwm_channel": 1, "writable": False}],
    )
    from app.core.exceptions import InvalidParamsError

    with pytest.raises(InvalidParamsError):
        await fan_manager.create_zone(db, {"name": "z", "loop": "cpu", "hwmon_name": "fan0", "pwm_channel": 1, "mode": "curve", "curve_id": None})
    # 未知芯片（测试环境/延迟枚举）不拦
    zid = await fan_manager.create_zone(
        db, {"name": "z2", "loop": "cpu", "hwmon_name": "no_such_chip", "pwm_channel": 2, "mode": "fixed"}
    )
    assert zid >= 1


async def test_update_zone_cannot_switch_to_curve_without_curve_id(db):
    """PUT 只传 mode=curve：结果态必须带 curve_id（曾可达成 curve missing 冻结态）。"""
    db.add(_zone(mode="fixed", fixed_pwm=40))
    await db.flush()

    from app.core.exceptions import InvalidParamsError

    with pytest.raises(InvalidParamsError):
        await fan_manager.update_zone(db, 1, {"mode": "curve"})


async def test_drive_zone_marks_critical_and_records_events(db):
    """临界全速带 critical 标记（前端弹提示）；事件环形缓冲留痕（A1/A5）。"""
    fan_manager._events.clear()
    db.add(_zone(mode="fixed", fixed_pwm=20, sensor_key="t"))
    await db.flush()

    entry = await fan_manager._drive_zone(db, await _first_zone(db), {"t": 91.0}, None)
    assert entry["critical"] is True and entry["target_pwm_pct"] == 100.0
    events = fan_manager.recent_events()
    assert events and events[0]["failsafe"] == "critical"
    assert "91" in events[0]["error"]


async def test_recent_events_ring_buffer_max_20():
    fan_manager._events.clear()
    for i in range(30):
        fan_manager._events.append({"ts": float(i), "zone_id": 1, "name": "z", "error": f"e{i}", "failsafe": None})
    events = fan_manager.recent_events()
    assert len(events) == 20 and events[0]["error"] == "e29"  # 最新在前


async def test_retry_restore_endpoint_semantics(db, monkeypatch):
    db.add(_zone(name="z"))
    await db.flush()

    calls = []
    monkeypatch.setattr(fan_manager.hwmon_driver, "restore_auto", lambda n, c: calls.append(n) or True)
    result = await fan_manager.retry_restore(db, 1)
    assert result == {"id": 1, "restored": True} and calls == ["no_such_chip"]

    monkeypatch.setattr(fan_manager.hwmon_driver, "restore_auto", lambda n, c: False)
    result = await fan_manager.retry_restore(db, 1)
    assert result == {"id": 1, "restored": False}
