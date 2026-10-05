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
from app.utils.async_cmd import run_cmd
from app.utils.validators import validate_device_name

router = APIRouter(prefix="/storage", tags=["storage"], dependencies=[ApiKeyDep, TrimAuthDep])


async def _disk_items(db: AsyncSession) -> list[DiskItem]:
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
async def get_volumes(db: AsyncSession = DbDep) -> list[dict]:
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
    """SMART 指标趋势序列（smart_15m 采集落库）。无数据返回空 points（盘接入后逐桶积累）。"""
    # 校验针对 lsblk 盘名（nvme0n1 合法、nvme0 非法），查询键回退控制器名（nvme0）
    name = smart_history.smart_key(validate_device_name(device))
    if metric not in smart_history.TRACKED_METRICS:
        raise NotFoundError(f"unknown smart metric: {metric}")
    return await smart_history.trend_series(db, name, metric, days)


@router.post("/self-tests", response_model=SelfTestState)
async def start_selftest(body: SelfTestIn) -> dict:
    device = validate_device_name(body.device)

    async def runner(dev: str, test_type: str) -> None:
        rc, _out, err = await run_cmd("smartctl", "-t", test_type, f"/dev/{dev}", timeout=120)
        if rc not in (0, 2):
            raise RuntimeError(err.strip()[:200] or f"smartctl -t rc={rc}")

    async def probe(dev: str) -> tuple[str, str | None]:
        """解析 smartctl -l selftest 最后一条记录 → (result, error)。

        只在预计时长到点后调用：此时本次自检大概率已写入日志，最后一条即本次，
        不做进行中轮询（日志无时间戳，轮询易把历史记录误判为本次结果）。
        """
        rc, out, _err = await run_cmd("smartctl", "-l", "selftest", f"/dev/{dev}", timeout=30)
        entries = [ln for ln in out.splitlines() if ln.lstrip().startswith("#")]
        if not entries:
            return "unknown", f"自检日志为空或不可读（smartctl rc={rc}）"
        last = entries[-1].lower()
        if "in progress" in last:
            return "unknown", "自检仍在进行，稍后刷新查看 smartctl 日志"
        if "completed without error" in last:
            return "completed", None
        if "aborted" in last or "interrupted" in last:
            return "aborted", "自检被中止（详情见 smartctl -l selftest）"
        if "completed" in last:  # Completed: read failure 等带错误的完成
            return "failed", "自检完成但报告错误（详情见 smartctl -l selftest）"
        return "unknown", None

    try:
        return self_test.start_test(device, body.type, runner, probe)
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
