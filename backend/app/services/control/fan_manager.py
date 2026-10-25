"""风扇统一管理：控区 CRUD + 调速输出（5s tick 由 medium_5s 任务驱动）。

failsafe 约定：本模块是原生 FCS 被接管后唯一的风扇管理方，任何单点故障
（传感器失联、曲线缺失、写失败）都不得让 PWM 静默冻结——要么保持上一值
并上报，要么按最坏情况全速。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidParamsError, NotFoundError
from app.db.session import session_factory
from app.models.control import FanCurve, FanZone
from app.services.control import curve_engine, hwmon_driver
from app.services.monitor.temperature import temperatures

logger = logging.getLogger(__name__)

FAILSAFE_AFTER_TICKS = 3  # 传感器连续失联达到该 tick 数（约 15s）后强制全速
CRITICAL_TEMP_C = 85.0  # 临界温度：无视曲线/迟滞/斜率，无条件全速
_sensor_fail_streak: dict[int, int] = {}


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
    if data.get("mode", "auto") != "auto":
        _validate_channel(data["hwmon_name"], data["pwm_channel"])
    zone = FanZone(**data)
    db.add(zone)
    await db.flush()
    return zone.id


def _validate_channel(hwmon_name: str, pwm_channel: int) -> None:
    """受管通道防呆（评审 2026-10-25 N4）：chip 在位但通道缺失/只读时拒绝——
    这类配置每 tick 必然写失败，PWM 滞留最后值且无人管理。chip 整体不在扫描
    结果中（测试环境/延迟枚举的芯片）不拦，交由首个调速 tick 如实上报。"""
    channels = hwmon_driver.scan_channels()
    match = next(
        (c for c in channels if c["chip"] == hwmon_name and c["pwm_channel"] == pwm_channel), None
    )
    if match is None:
        if any(c["chip"] == hwmon_name for c in channels):
            raise InvalidParamsError(f"hwmon {hwmon_name} 没有 pwm{pwm_channel} 通道")
        logger.info("hwmon 芯片 %s 不在当前扫描中，跳过通道校验", hwmon_name)
        return
    if not match["writable"]:
        raise InvalidParamsError(f"hwmon {hwmon_name} 的 pwm{pwm_channel} 为只读通道，不能受管")


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
    # curve 模式必须有曲线：否则调速 tick 每轮 "curve missing"，PWM 静默冻结
    # 在最后值（此状态曾可经 PUT 只传 mode 达成，评审 2026-10-25 P1-4）
    if zone.mode == "curve" and zone.curve_id is None and "mode" in patch:
        raise InvalidParamsError("curve 模式需要有效的 curve_id")
    if zone.mode != "auto" and ("mode" in patch or "hwmon_name" in patch or "pwm_channel" in patch):
        _validate_channel(zone.hwmon_name, zone.pwm_channel)
    result_zone: dict = {"id": zone.id, **changed}
    # 退出受管状态（切回 auto / 停用控区）时必须交还内核，否则 pwm_enable 滞留
    # 手动模式、占空比冻结在最后值且无人管理（禁用 ≠ 删除，删除走 delete_zone）
    if patch.get("mode") == "auto" or patch.get("enabled") is False:
        if not _restore_auto_logged(zone):
            result_zone["warning"] = "restore_auto failed：通道可能滞留手动模式"
        _sensor_fail_streak.pop(zone.id, None)
    await db.flush()
    return result_zone


def _restore_auto_logged(zone: FanZone) -> bool:
    """交还内核并检查结果：enable 写失败时风扇滞留手动+最后占空比，必须留痕
    （此前 4 处调用方全忽略返回值，失败零日志，评审 2026-10-25 P1-5）。"""
    ok = hwmon_driver.restore_auto(zone.hwmon_name, zone.pwm_channel)
    if not ok:
        logger.warning(
            "控区 %s(%s) 交还内核自动温控失败（%s pwm%s enable 写入失败），"
            "通道可能滞留手动模式与最后占空比",
            zone.id, zone.name, zone.hwmon_name, zone.pwm_channel,
        )
    return ok


async def delete_zone(db: AsyncSession, zone_id: int) -> None:
    result = await db.execute(select(FanZone).where(FanZone.id == zone_id))
    zone = result.scalar_one_or_none()
    if not zone:
        raise NotFoundError(f"fan zone {zone_id} not found")
    if zone.mode != "auto":
        _restore_auto_logged(zone)
    _sensor_fail_streak.pop(zone.id, None)
    await db.delete(zone)
    await db.flush()


async def release_curve(db: AsyncSession, curve_id: int) -> list[int]:
    """删除曲线前调用：引用该曲线的控区退回 auto 并交还硬件，避免调速 tick 悬空引用。"""
    result = await db.execute(select(FanZone).where(FanZone.curve_id == curve_id))
    released = []
    for zone in result.scalars():
        if zone.mode != "auto":
            _restore_auto_logged(zone)
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
            _restore_auto_logged(zone)  # 关停路径失败无人兜底，必须逐区留痕


async def apply_tick(db: AsyncSession, temp_items: list[dict] | None = None) -> list[dict]:
    """5s 调速输出：enabled 且非 auto 的控区按曲线/定速写 pwm（WS fans 事件数据源）。

    temp_items 由 medium_tick 传入（同轮采集复用，避免双扫描）；缺省时自行采集，
    采集异常按全传感器失联处理（空列表），让 failsafe streak 推进而非整轮跳过。
    """
    result = await db.execute(select(FanZone).where(FanZone.enabled.is_(True), FanZone.mode != "auto"))
    zones = result.scalars().all()
    if temp_items is None:
        temp_items = await _safe_temperatures()
    temps = {t["key"]: t["celsius"] for t in temp_items}
    # 默认传感器 = cpu zone 最高温（与 list_zones 口径一致）。此前回退取
    # next(iter(temps.values()))：ARM 机器上 NVMe 条目在前，CPU 风扇会跟盘温走
    cpu_default = max((t["celsius"] for t in temp_items if t["zone"] == "cpu"), default=None)
    outputs = []
    for zone in zones:
        try:
            outputs.append(await _drive_zone(db, zone, temps, cpu_default))
        except Exception as exc:  # noqa: BLE001 单控区故障不拖垮整轮调速与告警评估
            logger.warning("控区 %s(%s) 调速异常: %s", zone.id, zone.name, exc)
            outputs.append({"zone_id": zone.id, "name": zone.name, "mode": zone.mode, "error": str(exc)[:150]})
    return outputs


async def _safe_temperatures() -> list[dict]:
    try:
        return await temperatures()
    except Exception:  # noqa: BLE001 采集异常≠跳过调速：按全失联推进 failsafe
        logger.warning("温度采集异常，本轮调速按全传感器失联处理", exc_info=True)
        return []


def _sensor_temp_for(zone: FanZone, temps: dict[str, float | None], cpu_default: float | None) -> float | None:
    if zone.sensor_key:
        return temps.get(zone.sensor_key)
    return cpu_default


async def _drive_zone(
    db: AsyncSession, zone: FanZone, temps: dict[str, float | None], cpu_default: float | None = None
) -> dict:
    if zone.mode == "fixed":
        target = float(zone.fixed_pwm)
        # fixed 也要临界保护：手动定速不读温度的时代，85℃ 低占空比照跑（旧 P1-03）
        sensor_temp = _sensor_temp_for(zone, temps, cpu_default)
        if sensor_temp is not None and sensor_temp >= CRITICAL_TEMP_C:
            target = 100.0
    else:
        curve = await _find_curve(db, zone.curve_id) if zone.curve_id else None
        if curve is None:
            # 曲线缺失与传感器失联同级：PWM 静默冻结在最后值是最坏结局，走分级
            # failsafe（短暂保持→持续则全速），不再仅上报后放过（评审 P1-4）
            return await _failsafe_on_sensor_lost(zone, reason="curve missing")
        sensor_temp = _sensor_temp_for(zone, temps, cpu_default)
        if sensor_temp is None:
            return await _failsafe_on_sensor_lost(zone)
        _sensor_fail_streak.pop(zone.id, None)
        if sensor_temp >= CRITICAL_TEMP_C:
            target = 100.0  # 临界温度无条件全速
        else:
            # 当前占空比（0-255 原始值 → 0-100 pct）：迟滞与斜率限制的基准，
            # 不传则曲线引擎每 tick 可无阻尼跳变（审查 2026-09-30 P1）
            raw = hwmon_driver.read_pwm(zone.hwmon_name, zone.pwm_channel)
            current_pct = raw / 255 * 100 if raw is not None else None
            target = curve_engine.target_pwm(
                curve.points, sensor_temp, curve.hysteresis_c, int(curve.ramp_per_tick), current_pct
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
    if not ok:
        entry["error"] = "pwm write failed"
    return entry


async def _failsafe_on_sensor_lost(zone: FanZone, reason: str = "sensor unavailable") -> dict:
    """失联（传感器/曲线）分级兜底：短暂保持最后占空比并上报；持续失联按最坏情况全速。"""
    streak = _sensor_fail_streak.get(zone.id, 0) + 1
    _sensor_fail_streak[zone.id] = streak
    if streak < FAILSAFE_AFTER_TICKS:
        return {
            "zone_id": zone.id,
            "name": zone.name,
            "mode": zone.mode,
            "error": reason,
            "failsafe": "hold",
            "streak": streak,
        }
    ok = hwmon_driver.write_pwm(zone.hwmon_name, zone.pwm_channel, 100.0)
    entry = {
        "zone_id": zone.id,
        "name": zone.name,
        "mode": zone.mode,
        "target_pwm_pct": 100.0,
        "error": reason,
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
