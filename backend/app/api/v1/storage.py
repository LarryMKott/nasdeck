"""存储接口（契约 §3.2）。"""

from __future__ import annotations

from fastapi import APIRouter, Query
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
    SmartTrendResponse,
    VolumeItem,
)
from app.services.monitor import temperature
from app.services.storage import capacity, disk_name, self_test, smart, smart_history
from app.services.storage import raid as raid_service
from app.services.storage import volumes as volume_service
from app.utils.validators import validate_device_name

router = APIRouter(prefix="/storage", tags=["storage"], dependencies=[ApiKeyDep, TrimAuthDep])


async def _disk_items(db: AsyncSession) -> list[DiskItem]:
    """组装磁盘列表（含别名、SMART 健康与温度）。

    Args:
        db (AsyncSession): 数据库会话。

    Returns:
        list[DiskItem]: 见 schemas.storage.DiskItem。
    """
    disks = await volume_service.list_disks()
    aliases = await disk_name.get_alias_map(db)
    # 健康与温度来自 SMART 慢采集缓存（temperature 60s 一轮，零额外 fork）
    health_map = await temperature.disk_health()
    temps = await temperature.disk_temps()
    items = []
    for d in disks:
        d["alias"] = aliases.get(d.get("serial") or "")
        key = smart_history.smart_key(d.get("device") or "")
        d["health"] = health_map.get(key, "unknown")
        d["temp_c"] = temps.get(key)
        items.append(DiskItem(**d))
    return items


@router.get("/disks", response_model=list[DiskItem])
async def list_disks(db: AsyncSession = DbDep) -> list[DiskItem]:
    """列出全部物理磁盘（契约 §3.2）。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        list[DiskItem]: 见 schemas.storage.DiskItem。
    """
    return await _disk_items(db)


@router.get("/disks/{device}/smart", response_model=SmartReport)
async def get_smart(device: str) -> dict:
    """获取单盘 SMART 报告（契约 §3.2）。

    Args:
        device (str): 盘名（如 sda / nvme0n1，服务端校验防注入）。

    Returns:
        dict: 见 schemas.storage.SmartReport。

    Raises:
        InvalidParamsError: 盘名不合法时。
        ExternalToolError: smartctl 不可用或调用失败时。
    """
    name = validate_device_name(device)
    try:
        return await smart.smart_report(name)
    except ExternalToolError:
        raise
    except Exception as exc:
        raise ExternalToolError(f"smartctl failed: {exc}") from exc


@router.put("/disks/{serial}/alias", response_model=AliasOut)
async def put_alias(serial: str, body: AliasIn, db: AsyncSession = DbDep) -> dict:
    """设置磁盘别名（按序列号 upsert）。

    Args:
        serial (str): 磁盘序列号。
        body (AliasIn): 别名内容。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.storage.AliasOut。
    """
    alias = await disk_name.set_alias(db, serial, body.alias)
    return {"serial": serial, "alias": alias}


@router.delete("/disks/{serial}/alias", response_model=AliasDeleted)
async def delete_alias(serial: str, db: AsyncSession = DbDep) -> dict:
    """删除磁盘别名。

    Args:
        serial (str): 磁盘序列号。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.storage.AliasDeleted。
    """
    await disk_name.delete_alias(db, serial)
    return {"serial": serial, "deleted": True}


@router.get("/raid", response_model=RaidResponse)
async def get_raid() -> dict:
    """查询 RAID/阵列卡状态（无阵列卡时返回降级说明）。

    Returns:
        dict: 见 schemas.storage.RaidResponse。
    """
    return await raid_service.raid_status()


@router.get("/volumes", response_model=list[VolumeItem])
async def get_volumes(db: AsyncSession = DbDep) -> list[dict]:
    """列出存储卷（含写满预测）。

    Args:
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        list[dict]: 见 schemas.storage.VolumeItem（forecast 为容量回归预测，无采样记录时为 None）。
    """
    volumes = volume_service.list_volumes()
    # 写满预测（volume_15m 15 分钟一轮回归）按挂载点合并；无采样记录 forecast=None
    forecasts = {f["mount"]: f for f in await capacity.forecast_all(db)}
    for v in volumes:
        v["forecast"] = forecasts.get(v["mount"])
    return volumes


@router.get("/trend", response_model=SmartTrendResponse)
async def get_trend(
    device: str = Query(..., description="SMART 探测键（sda / nvme0）"),
    metric: str = Query("reallocated", description=f"指标名，白名单：{'/'.join(smart_history.TRACKED_METRICS)}"),
    days: int = Query(30, ge=1, le=90, description="窗口天数；≤30 用 1h 桶，否则 1d 桶"),
    db: AsyncSession = DbDep,
) -> dict:
    """SMART 指标趋势序列（smart_15m 采集落库）。

    无数据返回空 points（盘接入后逐桶积累）。

    Args:
        device (str): SMART 探测键（sda / nvme0）。
        metric (str): 指标名，白名单见 smart_history.TRACKED_METRICS。
        days (int): 窗口天数，1-90；≤30 用 1h 桶，否则 1d 桶。
        db (AsyncSession): 数据库会话（框架注入）。

    Returns:
        dict: 见 schemas.storage.SmartTrendResponse。

    Raises:
        InvalidParamsError: 盘名不合法时。
        NotFoundError: 指标不在白名单时。
    """
    # 校验针对 lsblk 盘名（nvme0n1 合法、nvme0 非法），查询键回退控制器名（nvme0）
    name = smart_history.smart_key(validate_device_name(device))
    if metric not in smart_history.TRACKED_METRICS:
        raise NotFoundError(f"unknown smart metric: {metric}")
    return await smart_history.trend_series(db, name, metric, days)


@router.post("/self-tests", response_model=SelfTestState)
async def start_selftest(body: SelfTestIn) -> dict:
    """发起 SMART 自检（short/long 等，单盘同时仅一个任务）。

    Args:
        body (SelfTestIn): 目标盘与自检类型。

    Returns:
        dict: 见 schemas.storage.SelfTestState。

    Raises:
        InvalidParamsError: 盘名不合法时。
        ExternalToolError: smartctl 不可用或自检任务启动超时时。
    """
    device = validate_device_name(body.device)
    try:
        return self_test.start_test(device, body.type)
    except Exception as exc:
        if "not found" in str(exc) or "timeout" in str(exc):
            raise ExternalToolError(f"smartctl 不可用: {exc}") from exc
        raise


@router.get("/self-tests", response_model=list[SelfTestState])
async def list_selftests() -> list[dict]:
    """列出进行中/历史自检任务。

    Returns:
        list[dict]: 见 schemas.storage.SelfTestState。
    """
    return self_test.list_tests()


@router.get("/self-tests/{device}", response_model=SelfTestState)
async def get_selftest(device: str) -> dict:
    """查询单盘自检状态。

    Args:
        device (str): 盘名。

    Returns:
        dict: 见 schemas.storage.SelfTestState。

    Raises:
        NotFoundError: 该盘无自检记录时。
    """
    try:
        return self_test.get_test(device)
    except KeyError as exc:
        raise NotFoundError(f"no self-test record for {device}") from exc
