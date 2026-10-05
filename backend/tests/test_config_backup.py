"""配置备份/恢复回归：导出脱敏、schema 版本拒绝、replace-all 导入、引用重映射。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.alert import AlertChannel, AlertRule
from app.models.control import FanCurve, FanZone
from app.models.system import SystemSetting
from app.services.system import backup


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(db):
    curve = FanCurve(name="默认曲线", points=[[40, 30], [70, 90]], hysteresis_c=2, ramp_per_tick=5)
    db.add(curve)
    await db.flush()
    db.add(FanZone(name="CPU_FAN", loop="cpu", hwmon_name="nct6798", pwm_channel=1,
                   mode="curve", curve_id=curve.id, enabled=True))
    db.add(AlertChannel(id=7, name="TG", type="telegram",
                        config={"bot_token": "123456:ABC-secret", "chat_id": "42"}))
    db.add(AlertRule(name="温度规则", metric="temp_max", comparator=">", threshold=60,
                     duration_ticks=6, severity="warning", channels=[7],
                     actions=["fan_full"], enabled=True))
    db.add(SystemSetting(key="fan_schedule", value={"enabled": True, "start": 23, "end": 7, "offset_c": 4}))
    await db.commit()


async def test_export_masks_secrets_by_default(db):
    await _seed(db)
    data = await backup.export_config(db)
    assert data["schema_version"] == backup.SCHEMA_VERSION
    ch = data["alert_channels"][0]
    assert ch["config_is_masked"] is True
    assert "ABC-secret" not in str(ch["config"])
    assert data["settings"]["fan_schedule"]["enabled"] is True

    plain = await backup.export_config(db, include_secrets=True)
    assert "123456:ABC-secret" in str(plain["alert_channels"][0]["config"])


async def test_import_rejects_bad_schema_version(db):
    with pytest.raises(Exception) as exc:
        await backup.import_config(db, {"schema_version": 99})
    assert "schema_version" in str(exc.value)


async def test_import_replace_all_with_remapping(db):
    await _seed(db)
    data = await backup.export_config(db, include_secrets=True)

    # 改变现场：删光 + 换名（验证 replace-all 与 id 重映射）
    from sqlalchemy import delete

    await db.execute(delete(FanZone))
    await db.execute(delete(FanCurve))
    await db.execute(delete(AlertRule))
    await db.execute(delete(AlertChannel))
    await db.commit()

    counts = await backup.import_config(db, data)
    await db.commit()
    assert counts["fan_zones"] == 1 and counts["alert_rules"] == 1

    zones = (await db.execute(select(FanZone))).scalars().all()
    curves = (await db.execute(select(FanCurve))).scalars().all()
    rules = (await db.execute(select(AlertRule))).scalars().all()
    channels = (await db.execute(select(AlertChannel))).scalars().all()
    assert len(zones) == 1 and len(curves) == 1 and len(rules) == 1 and len(channels) == 1

    # 引用重映射：zone.curve_id 指向新曲线 id；rule.channels 指向新渠道 id
    assert zones[0].curve_id == curves[0].id
    assert rules[0].channels == [channels[0].id]

    # 设置键带回
    row = await db.get(SystemSetting, "fan_schedule")
    assert row.value["offset_c"] == 4.0


async def test_import_drops_dangling_channel_refs(db):
    data = {
        "schema_version": 1,
        "alert_rules": [{"name": "r", "metric": "temp_max", "comparator": ">", "threshold": 1,
                         "duration_ticks": 1, "severity": "warning", "channels": [555],
                         "actions": [], "enabled": True}],
        "alert_channels": [],
    }
    counts = await backup.import_config(db, data)
    rules = (await db.execute(select(AlertRule))).scalars().all()
    assert counts["alert_rules"] == 1 and rules[0].channels == []  # 悬空引用剔除
