"""SMART 周期巡检：每周低峰时段逐盘串行自检，结果落事件、异常广播告警。

配置持久化 system_settings（key=selftest_schedule），10 分钟一拍的 tick 检查
命中（enabled ∧ 星期 ∧ 整点小时内 ∧ 本周未跑）即起独立 task 逐盘执行——
short 每盘约 2 分钟，task 化避免拖住调度轮。last_run 记 ISO 日期做周去重。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertEvent
from app.models.system import SystemSetting
from app.services.alert.engine import _enabled_channels, _queue_notify, schedule_drain
from app.services.storage import self_test, smart_history
from app.services.storage import volumes as volume_service

logger = logging.getLogger(__name__)

SCHEDULE_KEY = "selftest_schedule"
LAST_RUN_KEY = "selftest_last_run"

WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
VALID_TYPES = ("short", "long")

# 进程内防重入：tick 10 分钟一拍，一次巡检跨多拍时不得重复触发
_running: asyncio.Task | None = None


def default_schedule() -> dict:
    return {"enabled": False, "weekday": 6, "hour": 4, "type": "short"}  # 周日 04:00 UTC


async def load_schedule(db: AsyncSession) -> dict:
    row = await db.get(SystemSetting, SCHEDULE_KEY)
    merged = default_schedule()
    if row and isinstance(row.value, dict):
        merged.update({k: v for k, v in row.value.items() if k in merged})
    if merged["type"] not in VALID_TYPES:
        merged["type"] = "short"
    merged["weekday"] = max(0, min(6, int(merged["weekday"])))
    merged["hour"] = max(0, min(23, int(merged["hour"])))
    return merged


async def save_schedule(db: AsyncSession, cfg: dict) -> dict:
    row = await db.get(SystemSetting, SCHEDULE_KEY)
    if row:
        row.value = cfg
    else:
        db.add(SystemSetting(key=SCHEDULE_KEY, value=cfg, description="SMART 周期巡检计划"))
    await db.flush()
    return cfg


async def last_run_date(db: AsyncSession) -> str:
    row = await db.get(SystemSetting, LAST_RUN_KEY)
    return str(row.value) if row and row.value else ""


async def set_last_run_date(db: AsyncSession, day: str) -> None:
    row = await db.get(SystemSetting, LAST_RUN_KEY)
    if row:
        row.value = day
    else:
        db.add(SystemSetting(key=LAST_RUN_KEY, value=day, description="SMART 周期巡检上次运行日期"))
    await db.flush()


def _record_event(db: AsyncSession, *, severity: str, message: str, now: str) -> None:
    """巡检结果 → 事件历史（一次性记录，落库即 resolved，不占 firing 生命周期）。"""
    db.add(
        AlertEvent(
            rule_id=None,
            rule_name="SMART 周期巡检",
            metric="selftest",
            value=None,
            threshold=None,
            severity=severity,
            status="resolved",
            message=message,
            fired_at=now,
            resolved_at=now,
        )
    )


async def run_scheduled_selftest(db: AsyncSession) -> None:
    """逐盘串行发起自检并等待结果（进程内状态机复用，互斥保护生效）。"""
    disks = await volume_service.list_disks()
    devices = sorted({smart_history.smart_key(d.get("device") or "") for d in disks if d.get("device")})
    if not devices:
        logger.info("周期巡检：无磁盘可检，跳过")
        return
    cfg = await load_schedule(db)
    test_type = cfg["type"]
    channels = await _enabled_channels(db)
    now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    summary = []
    for dev in devices:
        try:
            state = self_test.start_test(dev, test_type)
        except Exception as exc:  # noqa: BLE001 单盘发起失败（含互斥）继续其余盘
            summary.append((dev, "failed", str(exc)[:150]))
            _record_event(db, severity="warning", message=f"{dev} 巡检发起失败：{exc}"[:200], now=now_str)
            continue
        # 状态机按预计时长推进，完成后经 probe 判定（轮询等待，上限 = 预计时长 + 5 分钟宽限）
        budget = {"short": 7, "long": 250, "conveyance": 10}[test_type] * 60
        waited = 0.0
        while state["status"] == "running" and waited < budget:
            await asyncio.sleep(15)
            waited += 15
            state = self_test.get_test(dev)
        result, error = state["result"], state["error"]
        ok = result == "completed"
        summary.append((dev, result, error))
        _record_event(
            db,
            severity="info" if ok else "warning",
            message=f"{dev} {test_type} 巡检 → {result}" + (f"（{error}）" if error else ""),
            now=now_str,
        )
        if not ok:
            _queue_notify(
                channels, list(channels.keys()),
                title=f"SMART 巡检异常 · {dev}",
                body=f"{dev} {test_type} 自检结果 {result}" + (f"：{error}" if error else ""),
            )
    await db.flush()
    logger.info("周期巡检完成：%s", "; ".join(f"{d}={r}" for d, r, _e in summary))


def _due(cfg: dict, now: datetime, last_run: str) -> bool:
    today = now.strftime("%Y-%m-%d")
    return now.weekday() == cfg["weekday"] and now.hour == cfg["hour"] and last_run != today


async def schedule_tick(db: AsyncSession, now: datetime | None = None) -> bool:
    """10 分钟一拍：命中计划窗口且未运行 → 起独立巡检 task。返回是否触发。

    tick 的请求级会话生命周期有限（自检可长达数小时），巡检 task 经
    _run_with_own_session 自建会话；last_run 先落库防同窗口重复触发。"""
    global _running
    if _running is not None and not _running.done():
        return False
    now = now or datetime.now(UTC)
    cfg = await load_schedule(db)
    if not cfg["enabled"] or not _due(cfg, now, await last_run_date(db)):
        return False
    await set_last_run_date(db, now.strftime("%Y-%m-%d"))
    _running = asyncio.create_task(_run_with_own_session())
    return True


async def _run_with_own_session() -> None:
    from app.db.session import session_factory

    async with session_factory() as db:
        try:
            await run_scheduled_selftest(db)
            await db.commit()
            schedule_drain()
        except Exception as exc:  # noqa: BLE001
            logger.warning("周期巡检异常: %s", exc)
            await db.rollback()
