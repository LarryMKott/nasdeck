"""风扇统一管理：控区 CRUD + 调速输出（5s tick 由 medium_5s 任务驱动）。

failsafe 约定：本模块是原生 FCS 被接管后唯一的风扇管理方，任何单点故障
（传感器失联、曲线缺失、写失败）都不得让 PWM 静默冻结——要么保持上一值
并上报，要么按最坏情况全速。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import session_factory
from app.models.control import FanCurve, FanZone
from app.services.control import curve_engine, hwmon_driver
from app.services.monitor.temperature import temperatures

logger = logging.getLogger(__name__)

FAILSAFE_AFTER_TICKS = 3  # 传感器连续失联达到该 tick 数（约 15s）后强制全速
CRITICAL_TEMP_C = 85.0  # 临界温度：无视曲线/迟滞/斜率，无条件全速
_sensor_fail_streak: dict[int, int] = {}

# 告警动作全速覆盖（IF-THEN 剧本引擎 fan_full）：窗口期内 _drive_zone 无条件 100%，
# 到期自动回落曲线接管——不落库，重启即失效（安全默认）
ALERT_FULL_MINUTES = 15
_alert_full_until = 0.0  # time.monotonic() 秒

# 时段静音计划（M2.5）：窗口期内曲线评估温度平移 -offset（等效目标温度 +offset，
# 曲线更平缓风扇更静）。持久化 system_settings key=fan_schedule；30s 进程内缓存。
# 失控保护优先级不变：传感器失联/临界温度判定用原始温度，发生在平移之前。
FAN_SCHEDULE_KEY = "fan_schedule"
_SCHEDULE_TTL_S = 30.0
_schedule_cache: dict = {"ts": 0.0, "data": None}


def _default_schedule() -> dict:
    return {"enabled": False, "start": 23, "end": 7, "offset_c": 4.0}


def _in_schedule_window(now_hour: int, start: int, end: int) -> bool:
    """支持跨午夜窗口（23→7）：start==end 视为全天，否则按环形区间判断。"""
    if start == end:
        return True
    return start <= now_hour < end if start < end else now_hour >= start or now_hour < end


def schedule_active(now_hour: int | None = None) -> bool:
    """纯函数：只读缓存（medium_5s 每轮 refresh_schedule_cache 刷新），调速轮零额外 IO。"""
    import datetime as _dt

    cfg = _schedule_cache["data"]
    if not cfg or not cfg.get("enabled"):
        return False
    hour = now_hour if now_hour is not None else _dt.datetime.now(_dt.UTC).hour
    return _in_schedule_window(hour, int(cfg["start"]), int(cfg["end"]))


def schedule_offset_c(now_hour: int | None = None) -> float:
    """窗口期内返回平移量，否则 0（curve 分支按此平移评估温度）。"""
    cfg = _schedule_cache["data"]
    return float(cfg["offset_c"]) if cfg and schedule_active(now_hour) else 0.0


async def _load_schedule() -> dict:
    from sqlalchemy import select as _select

    from app.models.system import SystemSetting

    async with session_factory() as db:
        row = (
            await db.execute(_select(SystemSetting).where(SystemSetting.key == FAN_SCHEDULE_KEY))
        ).scalar_one_or_none()
    cfg = _default_schedule()
    if row and isinstance(row.value, dict):
        cfg.update({k: v for k, v in row.value.items() if k in cfg})
    cfg["start"] = max(0, min(23, int(cfg["start"])))
    cfg["end"] = max(0, min(23, int(cfg["end"])))
    cfg["offset_c"] = max(0.0, min(15.0, float(cfg["offset_c"])))
    return cfg


async def refresh_schedule_cache() -> None:
    """medium_5s 每轮调用：30s TTL 限流读库；失败保持旧值（首轮失败=关闭态）。"""
    import time as _time

    now = _time.monotonic()
    if _schedule_cache["data"] is not None and now - _schedule_cache["ts"] < _SCHEDULE_TTL_S:
        return
    try:
        cfg = await _load_schedule()
        _schedule_cache.update(ts=now, data=cfg)
    except Exception:  # noqa: BLE001
        _schedule_cache["ts"] = now


async def get_schedule() -> dict:
    return await _load_schedule()


async def save_schedule(cfg: dict) -> dict:
    from sqlalchemy import select as _select

    from app.models.system import SystemSetting

    # 自管会话（不参与请求会话），必须自行 commit——flush 后关会话即回滚
    async with session_factory() as db:
        row = (
            await db.execute(_select(SystemSetting).where(SystemSetting.key == FAN_SCHEDULE_KEY))
        ).scalar_one_or_none()
        if row:
            row.value = cfg
        else:
            db.add(SystemSetting(key=FAN_SCHEDULE_KEY, value=cfg, description="时段静音计划"))
        await db.commit()
    _schedule_cache.update(ts=0.0, data=None)  # 失配缓存：下一拍（≤5s）即时生效
    return cfg


def request_full_speed(minutes: int = ALERT_FULL_MINUTES) -> float:
    """告警动作申请全速窗口；返回覆盖截止的 monotonic 时刻。"""
    global _alert_full_until
    import time

    _alert_full_until = max(_alert_full_until, time.monotonic() + minutes * 60)
    return _alert_full_until


def alert_full_active() -> bool:
    import time

    return time.monotonic() < _alert_full_until


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
    # sensor_key 与 curve_id 同为可空语义字段：显式 null 合法（清除调速依据）
    for key, value in patch.items():
        if value is not None or key in ("curve_id", "sensor_key"):
            setattr(zone, key, value)
            changed[key] = value
    # 退出受管状态（切回 auto / 停用控区）时必须交还内核，否则 pwm_enable 滞留
    # 手动模式、占空比冻结在最后值且无人管理（禁用 ≠ 删除，删除走 delete_zone）
    if patch.get("mode") == "auto" or patch.get("enabled") is False:
        hwmon_driver.restore_auto(zone.hwmon_name, zone.pwm_channel)
        _sensor_fail_streak.pop(zone.id, None)
    await db.flush()
    return {"id": zone.id, **changed}


async def delete_zone(db: AsyncSession, zone_id: int) -> None:
    result = await db.execute(select(FanZone).where(FanZone.id == zone_id))
    zone = result.scalar_one_or_none()
    if not zone:
        raise NotFoundError(f"fan zone {zone_id} not found")
    if zone.mode != "auto":
        hwmon_driver.restore_auto(zone.hwmon_name, zone.pwm_channel)
    _sensor_fail_streak.pop(zone.id, None)
    await db.delete(zone)
    await db.flush()


async def release_curve(db: AsyncSession, curve_id: int) -> list[int]:
    """删除曲线前调用：引用该曲线的控区退回 auto 并交还硬件，避免调速 tick 悬空引用。"""
    result = await db.execute(select(FanZone).where(FanZone.curve_id == curve_id))
    released = []
    for zone in result.scalars():
        if zone.mode != "auto":
            hwmon_driver.restore_auto(zone.hwmon_name, zone.pwm_channel)
        zone.mode = "auto"
        zone.curve_id = None
        _sensor_fail_streak.pop(zone.id, None)
        released.append(zone.id)
    if released:
        await db.flush()
    return released


async def restore_all_zones() -> None:
    """进程优雅关停前把受管控区交还内核自动温控，避免停机窗口风扇冻结在最后占空比。"""
    async with session_factory() as db:
        result = await db.execute(
            select(FanZone).where(FanZone.enabled.is_(True), FanZone.mode != "auto")
        )
        for zone in result.scalars():
            hwmon_driver.restore_auto(zone.hwmon_name, zone.pwm_channel)


async def apply_tick(db: AsyncSession) -> list[dict]:
    """5s 调速输出：enabled 且非 auto 的控区按曲线/定速写 pwm（WS fans 事件数据源）。"""
    result = await db.execute(select(FanZone).where(FanZone.enabled.is_(True), FanZone.mode != "auto"))
    zones = result.scalars().all()
    temps = {t["key"]: t["celsius"] for t in await temperatures()}
    outputs = []
    for zone in zones:
        try:
            outputs.append(await _drive_zone(db, zone, temps))
        except Exception as exc:  # noqa: BLE001 单控区故障不拖垮整轮调速与告警评估
            logger.warning("控区 %s(%s) 调速异常: %s", zone.id, zone.name, exc)
            outputs.append({"zone_id": zone.id, "name": zone.name, "mode": zone.mode, "error": str(exc)[:150]})
    return outputs


async def _drive_zone(db: AsyncSession, zone: FanZone, temps: dict[str, float | None]) -> dict:
    # 告警动作全速覆盖（fan_full 窗口）：优先级仅次于传感器失联 failsafe，
    # 高于定速/曲线/临界温度分支（临界本就 100%，行为一致）
    if alert_full_active():
        ok = hwmon_driver.write_pwm(zone.hwmon_name, zone.pwm_channel, 100.0)
        return {
            "zone_id": zone.id,
            "name": zone.name,
            "loop": zone.loop,
            "mode": zone.mode,
            "target_pwm_pct": 100.0,
            "current_rpm": hwmon_driver.read_rpm(zone.hwmon_name, zone.fan_channel) if zone.fan_channel else None,
            "alert_full": True,
            **({} if ok else {"error": "pwm write failed (alert_full)"}),
        }
    if zone.mode == "fixed":
        target, sensor_temp = float(zone.fixed_pwm), None
    else:
        curve = await _find_curve(db, zone.curve_id) if zone.curve_id else None
        if curve is None:
            return {"zone_id": zone.id, "name": zone.name, "mode": zone.mode, "error": "curve missing"}
        sensor_temp = temps.get(zone.sensor_key) if zone.sensor_key else next(
            (v for k, v in temps.items() if k.startswith("coretemp")), next(iter(temps.values()), None)
        )
        if sensor_temp is None:
            return await _failsafe_on_sensor_lost(zone)
        _sensor_fail_streak.pop(zone.id, None)
        if sensor_temp >= CRITICAL_TEMP_C:
            target = 100.0  # 临界温度无条件全速（原始温度判定，不受静音窗口平移影响）
        else:
            # 当前占空比（0-255 原始值 → 0-100 pct）：迟滞与斜率限制的基准，
            # 不传则曲线引擎每 tick 可无阻尼跳变（审查 2026-09-30 P1）
            raw = hwmon_driver.read_pwm(zone.hwmon_name, zone.pwm_channel)
            current_pct = raw / 255 * 100 if raw is not None else None
            offset = schedule_offset_c()
            target = curve_engine.target_pwm(
                curve.points, sensor_temp - offset, curve.hysteresis_c, int(curve.ramp_per_tick), current_pct
            )
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
    if schedule_offset_c() > 0:
        entry["quiet"] = True  # 静音窗口生效标记（FanView 提示用）
    if not ok:
        entry["error"] = "pwm write failed"
    return entry


async def _failsafe_on_sensor_lost(zone: FanZone) -> dict:
    """传感器失联：短暂失联保持最后占空比并上报；持续失联按最坏情况（过热）全速。"""
    streak = _sensor_fail_streak.get(zone.id, 0) + 1
    _sensor_fail_streak[zone.id] = streak
    if streak < FAILSAFE_AFTER_TICKS:
        return {
            "zone_id": zone.id,
            "name": zone.name,
            "mode": zone.mode,
            "error": "sensor unavailable",
            "failsafe": "hold",
            "streak": streak,
        }
    ok = hwmon_driver.write_pwm(zone.hwmon_name, zone.pwm_channel, 100.0)
    entry = {
        "zone_id": zone.id,
        "name": zone.name,
        "mode": zone.mode,
        "target_pwm_pct": 100.0,
        "error": "sensor unavailable",
        "failsafe": "full_speed",
        "streak": streak,
    }
    if not ok:
        entry["error"] = "pwm write failed (failsafe)"
    return entry


async def _require_curve(db: AsyncSession, curve_id: int) -> FanCurve:
    result = await db.execute(select(FanCurve).where(FanCurve.id == curve_id))
    curve = result.scalar_one_or_none()
    if not curve:
        raise NotFoundError(f"curve {curve_id} not found")
    return curve


async def _find_curve(db: AsyncSession, curve_id: int) -> FanCurve | None:
    """调速 tick 用：曲线缺失返回 None（控区级上报），不抛错中断。"""
    result = await db.execute(select(FanCurve).where(FanCurve.id == curve_id))
    return result.scalar_one_or_none()
