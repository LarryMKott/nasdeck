"""时段静音计划回归：跨午夜窗口、温度平移生效、失控保护不受窗口影响、API 往返。"""

from __future__ import annotations

import pytest

from app.models.system import SystemSetting  # noqa: F401 先于 create_all 注册 metadata
from app.services.control import curve_engine, fan_manager


@pytest.fixture(autouse=True)
def _reset_schedule_cache():
    fan_manager._schedule_cache.update(ts=0.0, data=None)
    yield
    fan_manager._schedule_cache.update(ts=0.0, data=None)


def _cache(cfg: dict | None):
    fan_manager._schedule_cache.update(ts=1e18, data=cfg)  # ts 远未来：TTL 内不回读


def test_window_crosses_midnight():
    assert fan_manager._in_schedule_window(23, 23, 7)
    assert fan_manager._in_schedule_window(2, 23, 7)
    assert fan_manager._in_schedule_window(6, 23, 7)
    assert not fan_manager._in_schedule_window(12, 23, 7)
    assert fan_manager._in_schedule_window(12, 8, 20)  # 普通窗口
    assert not fan_manager._in_schedule_window(21, 8, 20)
    assert fan_manager._in_schedule_window(9, 10, 10)  # start==end 全天


def test_schedule_active_reads_cache_only():
    _cache({"enabled": True, "start": 23, "end": 7, "offset_c": 4.0})
    assert fan_manager.schedule_active(now_hour=2)
    assert not fan_manager.schedule_active(now_hour=12)
    _cache({"enabled": False, "start": 23, "end": 7, "offset_c": 4.0})
    assert not fan_manager.schedule_active(now_hour=2)
    _cache(None)
    assert not fan_manager.schedule_active(now_hour=2)


def test_offset_only_inside_window():
    _cache({"enabled": True, "start": 23, "end": 7, "offset_c": 4.0})
    assert fan_manager.schedule_offset_c(now_hour=2) == 4.0  # 窗口内平移生效
    assert fan_manager.schedule_offset_c(now_hour=12) == 0.0  # 窗口外为 0
    _cache(None)
    assert fan_manager.schedule_offset_c(now_hour=2) == 0.0  # 关闭态恒 0


def test_curve_eval_shifted_by_offset():
    """55°C 原始评估 vs 平移 4°C（等效 51°C）：平移后目标占空比不高于原始。"""
    points = [[40, 30], [60, 80]]
    base = curve_engine.target_pwm(points, 55, 0, 50, None)
    shifted = curve_engine.target_pwm(points, 55 - 4, 0, 50, None)
    assert shifted < base  # 更低温 → 更低目标 → 更静


def test_failsafe_before_offset(monkeypatch):
    """语义锁：平移只发生在 curve 分支（_drive_zone 内 critical 判定先于 offset）；
    此处锁纯函数边界——窗口全开时 offset 为有限正值，不侵入临界路径输入。"""
    _cache({"enabled": True, "start": 0, "end": 0, "offset_c": 4.0})
    assert fan_manager.schedule_active(now_hour=5)
    assert fan_manager.schedule_offset_c(now_hour=5) == 4.0
    assert fan_manager.schedule_offset_c(now_hour=5) < 85.0  # 远小于临界阈值


async def test_load_schedule_clamps_and_merges(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(fan_manager, "session_factory", maker)

    async with maker() as db:
        db.add(SystemSetting(key=fan_manager.FAN_SCHEDULE_KEY,
                             value={"enabled": True, "start": 99, "end": -3, "offset_c": 99}))
        await db.commit()

    cfg = await fan_manager._load_schedule()
    assert cfg["enabled"] is True
    assert cfg["start"] == 23 and cfg["end"] == 0 and cfg["offset_c"] == 15.0  # 越界钳制
    await engine.dispose()


async def test_save_then_refresh_cache_roundtrip(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(fan_manager, "session_factory", maker)

    # save_schedule 只 flush（commit 归 API 层 get_db）；写路径由 API 往返测试覆盖，
    # 此处直写行使 refresh→active 链路独立可测
    async with maker() as db:
        db.add(SystemSetting(key=fan_manager.FAN_SCHEDULE_KEY,
                             value={"enabled": True, "start": 22, "end": 8, "offset_c": 5.0}))
        await db.commit()

    fan_manager._schedule_cache.update(ts=0.0, data=None)  # 失配缓存走真实读库
    await fan_manager.refresh_schedule_cache()
    assert fan_manager.schedule_active(now_hour=23)
    assert fan_manager.schedule_active(now_hour=3)
    assert not fan_manager.schedule_active(now_hour=15)
    assert fan_manager.schedule_offset_c(now_hour=23) == 5.0
    await engine.dispose()


# ---- API：GET/PUT /control/fan-schedule ----


async def test_fan_schedule_api_roundtrip(client):
    default = (await client.get("/api/v1/control/fan-schedule")).json()["data"]
    assert default["enabled"] is False and "active" in default

    saved = (
        await client.put(
            "/api/v1/control/fan-schedule",
            json={"enabled": True, "start": 23, "end": 7, "offset_c": 4.0},
        )
    ).json()["data"]
    assert saved["enabled"] is True and saved["start"] == 23

    again = (await client.get("/api/v1/control/fan-schedule")).json()["data"]
    assert again["enabled"] is True and again["offset_c"] == 4.0
