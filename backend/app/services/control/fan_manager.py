"""风扇统一管理：控区 CRUD + 调速输出（5s tick 由 medium_5s 任务驱动）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.control import FanCurve, FanZone
from app.services.control import curve_engine, hwmon_driver
from app.services.monitor.temperature import temperatures


async def list_zones(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(FanZone).order_by(FanZone.id))
    temp_items = await temperatures()
    temps = {t["key"]: t["celsius"] for t in temp_items}
    cpu_items = [t for t in temp_items if t["zone"] == "cpu"]
    default_temp = max((t["celsius"] for t in cpu_items), default=None)
    zones = []
    for zone in result.scalars():
        raw_pwm = hwmon_driver.read_pwm(zone.hwmon_name, zone.pwm_channel)
        rpm = hwmon_driver.read_rpm(zone.hwmon_name, zone.fan_channel) if zone.fan_channel else None
        sensor_temp = temps.get(zone.sensor_key) if zone.sensor_key else default_temp
        zones.append(
            {
                "id": zone.id,
                "name": zone.name,
                "loop": zone.loop,
                "hwmon_name": zone.hwmon_name,
                "pwm_channel": zone.pwm_channel,
                "mode": zone.mode,
                "fixed_pwm": zone.fixed_pwm,
                "curve_id": zone.curve_id,
                "enabled": zone.enabled,
                "sensor_key": zone.sensor_key,
                "current_pwm_pct": round(raw_pwm / 255 * 100, 1) if raw_pwm is not None else None,
                "current_rpm": rpm,
                "sensor_temp_c": sensor_temp,
            }
        )
    return zones


async def create_zone(db: AsyncSession, data: dict) -> int:
    if data.get("curve_id") is not None:
        await _require_curve(db, data["curve_id"])
    zone = FanZone(**data)
    db.add(zone)
    await db.flush()
    return zone.id


async def update_zone(db: AsyncSession, zone_id: int, patch: dict) -> dict:
    result = await db.execute(select(FanZone).where(FanZone.id == zone_id))
    zone = result.scalar_one_or_none()
    if not zone:
        raise NotFoundError(f"fan zone {zone_id} not found")
    if patch.get("curve_id") is not None:
        await _require_curve(db, patch["curve_id"])
    changed = {}
    for key, value in patch.items():
        if value is not None or key == "curve_id":
            setattr(zone, key, value)
            changed[key] = value
    if patch.get("mode") == "auto":
        hwmon_driver.restore_auto(zone.hwmon_name, zone.pwm_channel)
    await db.flush()
    return {"id": zone.id, **changed}


async def delete_zone(db: AsyncSession, zone_id: int) -> None:
    result = await db.execute(select(FanZone).where(FanZone.id == zone_id))
    zone = result.scalar_one_or_none()
    if not zone:
        raise NotFoundError(f"fan zone {zone_id} not found")
    if zone.mode != "auto":
        hwmon_driver.restore_auto(zone.hwmon_name, zone.pwm_channel)
    await db.delete(zone)
    await db.flush()


async def apply_tick(db: AsyncSession) -> list[dict]:
    """5s 调速输出：enabled 且非 auto 的控区按曲线/定速写 pwm（WS fans 事件数据源）。"""
    result = await db.execute(select(FanZone).where(FanZone.enabled.is_(True), FanZone.mode != "auto"))
    zones = result.scalars().all()
    temps = {t["key"]: t["celsius"] for t in await temperatures()}
    outputs = []
    for zone in zones:
        if zone.mode == "fixed":
            target = float(zone.fixed_pwm)
            sensor_temp = None
        else:
            curve = await _require_curve(db, zone.curve_id) if zone.curve_id else None
            if curve is None:
                continue
            sensor_temp = temps.get(zone.sensor_key) if zone.sensor_key else next(
                (v for k, v in temps.items() if k.startswith("coretemp")), next(iter(temps.values()), None)
            )
            if sensor_temp is None:
                outputs.append(
                    {"zone_id": zone.id, "mode": zone.mode, "error": "sensor unavailable"}
                )
                continue
            target = curve_engine.target_pwm(curve.points, sensor_temp, curve.hysteresis_c, int(curve.ramp_per_tick))
        ok = hwmon_driver.write_pwm(zone.hwmon_name, zone.pwm_channel, target)
        entry = {
            "zone_id": zone.id,
            "name": zone.name,
            "loop": zone.loop,
            "mode": zone.mode,
            "target_pwm_pct": target,
            "current_rpm": hwmon_driver.read_rpm(zone.hwmon_name, zone.fan_channel) if zone.fan_channel else None,
        }
        if sensor_temp is not None:
            entry["sensor_temp_c"] = sensor_temp
        if not ok:
            entry = {"zone_id": zone.id, "error": "pwm write failed"}
        outputs.append(entry)
    return outputs


async def _require_curve(db: AsyncSession, curve_id: int) -> FanCurve:
    result = await db.execute(select(FanCurve).where(FanCurve.id == curve_id))
    curve = result.scalar_one_or_none()
    if not curve:
        raise NotFoundError(f"curve {curve_id} not found")
    return curve
