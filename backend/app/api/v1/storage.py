"""存储接口（契约 §3.2）。"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiKeyDep, DbDep, TrimAuthDep
from app.core.exceptions import ExternalToolError, NotFoundError
from app.schemas.storage import (
    AliasDeleted,
    AliasIn,
    AliasOut,
    DiskItem,
    RaidResponse,
    SelfTestIn,
    SelfTestState,
    SmartReport,
    VolumeItem,
)
from app.services.storage import disk_name, self_test, smart
from app.services.storage import raid as raid_service
from app.services.storage import volumes as volume_service
from app.utils.async_cmd import run_cmd
from app.utils.validators import validate_device_name

router = APIRouter(prefix="/storage", tags=["storage"], dependencies=[ApiKeyDep, TrimAuthDep])


async def _disk_items(db: AsyncSession) -> list[DiskItem]:
    disks = await volume_service.list_disks()
    aliases = await disk_name.get_alias_map(db)
    items = []
    for d in disks:
        d["alias"] = aliases.get(d.get("serial") or "")
        d.setdefault("health", "unknown")
        items.append(DiskItem(**d))
    return items


@router.get("/disks", response_model=list[DiskItem])
async def list_disks(db: AsyncSession = DbDep) -> list[DiskItem]:
    return await _disk_items(db)


@router.get("/disks/{device}/smart", response_model=SmartReport)
async def get_smart(device: str) -> dict:
    name = validate_device_name(device)
    try:
        return await smart.smart_report(name)
    except ExternalToolError:
        raise
    except Exception as exc:
        raise ExternalToolError(f"smartctl failed: {exc}") from exc


@router.put("/disks/{serial}/alias", response_model=AliasOut)
async def put_alias(serial: str, body: AliasIn, db: AsyncSession = DbDep) -> dict:
    alias = await disk_name.set_alias(db, serial, body.alias)
    return {"serial": serial, "alias": alias}


@router.delete("/disks/{serial}/alias", response_model=AliasDeleted)
async def delete_alias(serial: str, db: AsyncSession = DbDep) -> dict:
    await disk_name.delete_alias(db, serial)
    return {"serial": serial, "deleted": True}


@router.get("/raid", response_model=RaidResponse)
async def get_raid() -> dict:
    return await raid_service.raid_status()


@router.get("/volumes", response_model=list[VolumeItem])
async def get_volumes() -> list[dict]:
    return volume_service.list_volumes()


@router.post("/self-tests", response_model=SelfTestState)
async def start_selftest(body: SelfTestIn) -> dict:
    device = validate_device_name(body.device)

    async def runner(dev: str, test_type: str) -> None:
        rc, _out, err = await run_cmd("smartctl", "-t", test_type, f"/dev/{dev}", timeout=120)
        if rc not in (0, 2):
            raise RuntimeError(err.strip()[:200] or f"smartctl -t rc={rc}")

    try:
        return self_test.start_test(device, body.type, runner)
    except Exception as exc:
        if "not found" in str(exc) or "timeout" in str(exc):
            raise ExternalToolError(f"smartctl 不可用: {exc}") from exc
        raise


@router.get("/self-tests", response_model=list[SelfTestState])
async def list_selftests() -> list[dict]:
    return self_test.list_tests()


@router.get("/self-tests/{device}", response_model=SelfTestState)
async def get_selftest(device: str) -> dict:
    try:
        return self_test.get_test(device)
    except KeyError as exc:
        raise NotFoundError(f"no self-test record for {device}") from exc
