"""风扇控制接口（契约 §3.4）。"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiKeyDep, DbDep, TrimAuthDep
from app.core.exceptions import NotFoundError
from app.models.control import FanCurve
from app.schemas.control import (
    CurveIn,
    CurveItem,
    FanScheduleIn,
    FanScheduleOut,
    FanZoneIn,
    FanZoneItem,
    FanZoneUpdate,
    FcsStatus,
    HwmonChannel,
)
from app.services.control import curve_engine, fan_manager, fcs_safe_takeover, hwmon_driver

router = APIRouter(prefix="/control", tags=["control"], dependencies=[ApiKeyDep, TrimAuthDep])


@router.get("/hwmon/channels", response_model=list[HwmonChannel])
async def hwmon_channels() -> list[dict]:
    """列出 hwmon 风控芯片的可调通道（契约 §3.4）。

    Returns:
        list[dict]: 见 schemas.control.HwmonChannel。
    """
    return hwmon_driver.scan_channels()


@router.get("/fans", response_model=list[FanZoneItem])
async def list_fans(db: AsyncSession = DbDep) -> list[dict]:
    """列出全部风扇控区。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        list[dict]: 见 schemas.control.FanZoneItem。
    """
    return await fan_manager.list_zones(db)


@router.post("/fans")
async def create_fan(body: FanZoneIn, db: AsyncSession = DbDep) -> dict:
    """创建风扇控区。

    Args:
        body (FanZoneIn): 控区字段（名称/PWM 通道/调速依据等）。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 新控区 id}``。
    """
    zone_id = await fan_manager.create_zone(db, body.model_dump())
    return {"id": zone_id}


@router.put("/fans/{zone_id}")
async def update_fan(zone_id: int, body: FanZoneUpdate, db: AsyncSession = DbDep) -> dict:
    """局部更新风扇控区（仅应用请求体显式给出的字段）。

    Args:
        zone_id (int): 控区 id。
        body (FanZoneUpdate): 允许更新的字段子集。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 更新后的控区数据（形状见 schemas.control.FanZoneItem）。

    Raises:
        NotFoundError: 控区不存在时。
    """
    # exclude_unset：只应用请求体显式出现的字段，未提及的 curve_id/sensor_key 不得被默认值清掉；
    # 这两者为可空语义字段，显式 null = 清除（调速依据回退 CPU 最高温）
    patch = {
        k: v
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None or k in ("curve_id", "sensor_key")
    }
    return await fan_manager.update_zone(db, zone_id, patch)


@router.delete("/fans/{zone_id}")
async def delete_fan(zone_id: int, db: AsyncSession = DbDep) -> dict:
    """删除风扇控区并交还硬件控制。

    Args:
        zone_id (int): 控区 id。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 控区 id, "deleted": True}``。

    Raises:
        NotFoundError: 控区不存在时。
    """
    await fan_manager.delete_zone(db, zone_id)
    return {"id": zone_id, "deleted": True}


async def _curve_or_404(db: AsyncSession, curve_id: int) -> FanCurve:
    """按 id 取风扇曲线，不存在即抛 404。

    Args:
        db (AsyncSession): 数据库会话。
        curve_id (int): 曲线 id。

    Returns:
        FanCurve: 曲线 ORM 对象。

    Raises:
        NotFoundError: 曲线不存在时。
    """
    result = await db.execute(select(FanCurve).where(FanCurve.id == curve_id))
    curve = result.scalar_one_or_none()
    if not curve:
        raise NotFoundError(f"curve {curve_id} not found")
    return curve


@router.get("/curves", response_model=list[CurveItem])
async def list_curves(db: AsyncSession = DbDep) -> list[dict]:
    """列出全部风扇曲线，按 id 升序。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        list[dict]: 见 schemas.control.CurveItem。
    """
    result = await db.execute(select(FanCurve).order_by(FanCurve.id))
    return [
        {"id": c.id, "name": c.name, "points": c.points,
         "hysteresis_c": c.hysteresis_c, "ramp_per_tick": c.ramp_per_tick}
        for c in result.scalars()
    ]


@router.post("/curves")
async def create_curve(body: CurveIn, db: AsyncSession = DbDep) -> dict:
    """创建风扇曲线。

    Args:
        body (CurveIn): 曲线字段（名称/温度-PWM 点位/迟滞等）。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 新曲线 id}``。
    """
    curve = FanCurve(**body.model_dump())
    db.add(curve)
    await db.flush()
    return {"id": curve.id}


@router.put("/curves/{curve_id}")
async def update_curve(curve_id: int, body: CurveIn, db: AsyncSession = DbDep) -> dict:
    """整体更新风扇曲线（全字段覆盖）。

    Args:
        curve_id (int): 曲线 id。
        body (CurveIn): 新的曲线字段。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 曲线 id}``。

    Raises:
        NotFoundError: 曲线不存在时。
    """
    curve = await _curve_or_404(db, curve_id)
    for key, value in body.model_dump().items():
        setattr(curve, key, value)
    await db.flush()
    return {"id": curve.id}


@router.delete("/curves/{curve_id}")
async def delete_curve(curve_id: int, db: AsyncSession = DbDep) -> dict:
    """删除风扇曲线，引用它的控区先退回 auto。

    Args:
        curve_id (int): 曲线 id。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"id": 曲线 id, "deleted": True, "zones_released": 释放的控区数}``。

    Raises:
        NotFoundError: 曲线不存在时。
    """
    curve = await _curve_or_404(db, curve_id)
    # 引用该曲线的控区先退回 auto 并交还硬件：悬空 curve_id 会让调速 tick 持续失败
    released = await fan_manager.release_curve(db, curve_id)
    await db.delete(curve)
    await db.flush()
    return {"id": curve_id, "deleted": True, "zones_released": released}


@router.get("/curves/preview")
async def preview_curve(
    curve_id: int = Query(...),
    temp: float = Query(..., alias="temp"),
    db: AsyncSession = DbDep,
) -> dict:
    """预览指定温度下曲线的目标 PWM（不落库、不生效）。

    Args:
        curve_id (int): 曲线 id（query 参数）。
        temp (float): 模拟温度（℃）。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: ``{"temp_c": 温度, "target_pwm_pct": 目标 PWM 百分比}``。

    Raises:
        NotFoundError: 曲线不存在时。
    """
    curve = await _curve_or_404(db, curve_id)
    return {"temp_c": temp, "target_pwm_pct": curve_engine.preview(curve.points, temp)}


@router.get("/fcs", response_model=FcsStatus)
async def fcs_status() -> dict:
    """查询 FCS（主板风扇控制服务）接管状态。

    Returns:
        dict: 见 schemas.control.FcsStatus。
    """
    return await fcs_safe_takeover.status()


@router.post("/fcs/takeover")
async def fcs_takeover() -> dict:
    """接管 FCS 风扇控制，改由 nasdeck 调速。

    Returns:
        dict: 见 schemas.control.FcsStatus。
    """
    return await fcs_safe_takeover.takeover()


@router.post("/fcs/release")
async def fcs_release() -> dict:
    """释放 FCS 控制权，交还主板自动调速。

    Returns:
        dict: 见 schemas.control.FcsStatus。
    """
    return await fcs_safe_takeover.release()

@router.get("/fan-schedule", response_model=FanScheduleOut)
async def get_fan_schedule(db: AsyncSession = DbDep) -> dict:
    """查询时段静音计划及当前是否处于静音时段。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.control.FanScheduleOut（含 active 标记）。
    """
    cfg = await fan_manager.get_schedule()
    cfg["active"] = fan_manager.schedule_active()
    return cfg


@router.put("/fan-schedule", response_model=FanScheduleOut)
async def put_fan_schedule(body: FanScheduleIn, db: AsyncSession = DbDep) -> dict:
    """保存时段静音计划。

    写操作仅管理员，路由级 trim 鉴权强校验。保存后下一调速轮（≤5s）生效。

    Args:
        body (FanScheduleIn): 计划开关与生效时段。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.control.FanScheduleOut（含 active 标记）。
    """
    cfg = await fan_manager.save_schedule(body.model_dump())
    cfg["active"] = fan_manager.schedule_active()
    return cfg
