"""风扇控制接口（契约 §3.4）。"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiKeyDep, DbDep
from app.core.exceptions import NotFoundError
from app.models.control import FanCurve
from app.schemas.control import (
    CurveIn,
    CurveItem,
    FanZoneIn,
    FanZoneItem,
    FanZoneUpdate,
    FcsStatus,
    HwmonChannel,
)
from app.services.control import curve_engine, fan_manager, fcs_safe_takeover, hwmon_driver

router = APIRouter(prefix="/control", tags=["control"], dependencies=[ApiKeyDep])


@router.get("/hwmon/channels", response_model=list[HwmonChannel])
async def hwmon_channels() -> list[dict]:
    return hwmon_driver.scan_channels()


@router.get("/fans", response_model=list[FanZoneItem])
async def list_fans(db: AsyncSession = DbDep) -> list[dict]:
    return await fan_manager.list_zones(db)


@router.post("/fans")
async def create_fan(body: FanZoneIn, db: AsyncSession = DbDep) -> dict:
    zone_id = await fan_manager.create_zone(db, body.model_dump())
    return {"id": zone_id}


@router.put("/fans/{zone_id}")
async def update_fan(zone_id: int, body: FanZoneUpdate, db: AsyncSession = DbDep) -> dict:
    patch = {k: v for k, v in body.model_dump().items() if v is not None or k == "curve_id"}
    return await fan_manager.update_zone(db, zone_id, patch)


@router.delete("/fans/{zone_id}")
async def delete_fan(zone_id: int, db: AsyncSession = DbDep) -> dict:
    await fan_manager.delete_zone(db, zone_id)
    return {"id": zone_id, "deleted": True}


async def _curve_or_404(db: AsyncSession, curve_id: int) -> FanCurve:
    result = await db.execute(select(FanCurve).where(FanCurve.id == curve_id))
    curve = result.scalar_one_or_none()
    if not curve:
        raise NotFoundError(f"curve {curve_id} not found")
    return curve


@router.get("/curves", response_model=list[CurveItem])
async def list_curves(db: AsyncSession = DbDep) -> list[dict]:
    result = await db.execute(select(FanCurve).order_by(FanCurve.id))
    return [
        {"id": c.id, "name": c.name, "points": c.points,
         "hysteresis_c": c.hysteresis_c, "ramp_per_tick": c.ramp_per_tick}
        for c in result.scalars()
    ]


@router.post("/curves")
async def create_curve(body: CurveIn, db: AsyncSession = DbDep) -> dict:
    curve = FanCurve(**body.model_dump())
    db.add(curve)
    await db.flush()
    return {"id": curve.id}


@router.put("/curves/{curve_id}")
async def update_curve(curve_id: int, body: CurveIn, db: AsyncSession = DbDep) -> dict:
    curve = await _curve_or_404(db, curve_id)
    for key, value in body.model_dump().items():
        setattr(curve, key, value)
    await db.flush()
    return {"id": curve.id}


@router.delete("/curves/{curve_id}")
async def delete_curve(curve_id: int, db: AsyncSession = DbDep) -> dict:
    curve = await _curve_or_404(db, curve_id)
    await db.delete(curve)
    await db.flush()
    return {"id": curve_id, "deleted": True}


@router.get("/curves/preview")
async def preview_curve(
    curve_id: int = Query(...),
    temp: float = Query(..., alias="temp"),
    db: AsyncSession = DbDep,
) -> dict:
    curve = await _curve_or_404(db, curve_id)
    return {"temp_c": temp, "target_pwm_pct": curve_engine.preview(curve.points, temp)}


@router.get("/fcs", response_model=FcsStatus)
async def fcs_status() -> dict:
    return await fcs_safe_takeover.status()


@router.post("/fcs/takeover")
async def fcs_takeover() -> dict:
    return await fcs_safe_takeover.takeover()


@router.post("/fcs/release")
async def fcs_release() -> dict:
    return await fcs_safe_takeover.release()
