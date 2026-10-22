"""硬盘只读跑分（花活二期 Q）：O_DIRECT 顺序读基准 + 占空比限速 + 成绩落库。

护栏（提案约定）：仅管理员手动触发（写端点经路由级非 GET 强校验）；全局同一
时间只跑一个（进程内状态机，重复触发 1005）；standby 盘默认跳过不唤醒
（smartctl -n standby 探测，休眠即拒）；块间微休眠把 IO 占用压到 duty%（默认 30）；
不做定时任务、不做排队——基准期间业务盘延迟上升是物理规律，护栏只能减不能免。

读路径：os.preadv + O_DIRECT（mmap 页对齐缓冲）绕页缓存；盘尾回卷循环读。
非 Linux 主机直接拒绝。成绩在首次被观测（current()/history()）时惰性落库。
"""

from __future__ import annotations

import mmap
import os
import platform
import threading
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ExternalToolError, StateConflictError
from app.models.storage import BenchResult
from app.services.storage import smart as smart_service
from app.services.storage import volumes as volume_service
from app.utils.validators import validate_device_name

BLK = 1024 * 1024  # 1 MiB 块（4096 对齐倍数）
SAMPLE_WIN = 0.5  # 采样/限速周期（秒）
MIN_SECONDS, MAX_SECONDS = 5, 120
MIN_DUTY, MAX_DUTY = 10, 100
CURVE_CAP = 64

# 进程内状态机：全局唯一跑分（单 worker 线程写，asyncio 侧读）
_state: dict = {
    "status": "idle",  # idle/running/done/error
    "device": None,
    "seconds": 20,
    "duty": 30,
    "direct": False,
    "stop": False,
    "started_at": None,  # ISO 串
    "elapsed": 0.0,
    "progress": 0.0,
    "bps": 0.0,
    "curve": [],  # [{t 秒, mbps}]（≤CURVE_CAP）
    "bytes_read": 0,
    "error": None,
    "result_id": None,  # 惰性落库后的成绩行 id
}


def reset_for_test() -> None:
    """清空状态机（测试隔离）。"""
    for k, v in {
        "status": "idle",
        "device": None,
        "stop": False,
        "elapsed": 0.0,
        "progress": 0.0,
        "bps": 0.0,
        "curve": [],
        "bytes_read": 0,
        "error": None,
        "result_id": None,
    }.items():
        _state[k] = v


def current() -> dict:
    """状态机快照（前端 1s 轮询数据面；内部句柄不透出）。"""
    return {
        "status": _state["status"],
        "device": _state["device"],
        "seconds": _state["seconds"],
        "duty": _state["duty"],
        "direct": _state["direct"],
        "started_at": _state["started_at"],
        "elapsed": round(_state["elapsed"], 1),
        "progress": round(_state["progress"], 1),
        "bps": round(_state["bps"], 1),
        "curve": list(_state["curve"]),
        "bytes_read": _state["bytes_read"],
        "error": _state["error"],
        "result_id": _state["result_id"],
    }


async def start(device: str, seconds: int = 20, duty: int = 30) -> dict:
    """触发一次跑分（管理员；全局互斥）。

    Args:
        device (str): 盘名（不带 /dev/，经 validate_device_name 归一）。
        seconds (int): 基准时长（5-120s）。
        duty (int): 读占用百分比（10-100，越低对业务越友好、成绩越保守）。

    Returns:
        dict: current() 快照（status=running）。

    Raises:
        InvalidParamsError: 盘名/参数不合法，或非 Linux 主机。
        NotFoundError: 盘不在系统盘清单。
        StateConflictError: 已有跑分在跑（1005），或盘处于 standby（不唤醒）。
    """
    device = validate_device_name(device)
    seconds = max(MIN_SECONDS, min(MAX_SECONDS, int(seconds)))
    duty = max(MIN_DUTY, min(MAX_DUTY, int(duty)))
    if platform.system() != "Linux":
        raise ExternalToolError("跑分基准仅支持 Linux 主机（O_DIRECT 块设备直读）")
    if _state["status"] == "running":
        raise StateConflictError(f"已有跑分在执行（{_state['device']}），同一时间仅允许一个")

    disks = await volume_service.list_disks()
    if not any(d.get("device") == device for d in disks):
        from app.core.exceptions import NotFoundError

        raise NotFoundError(f"盘 {device} 不在系统盘清单")
    try:
        report = await smart_service.smart_report(device)
    except Exception:  # noqa: BLE001 smartctl 缺失等：无法预判休眠，交由实测（读会转起盘）
        report = {}
    if report.get("standby"):
        raise StateConflictError(f"盘 {device} 处于休眠（standby），已跳过不唤醒；请先手动激活后再跑分")

    _state.update(
        status="running",
        device=device,
        seconds=seconds,
        duty=duty,
        stop=False,
        started_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        elapsed=0.0,
        progress=0.0,
        bps=0.0,
        curve=[],
        bytes_read=0,
        error=None,
        result_id=None,
    )
    threading.Thread(target=_worker, args=(device, seconds, duty), daemon=True).start()
    return current()


def cancel() -> dict:
    """请求取消当前跑分（协作式：worker 在下一个块间检查到即收尾）。"""
    if _state["status"] == "running":
        _state["stop"] = True
    return current()


async def maybe_persist(db: AsyncSession) -> None:
    """done 且未落库 → 写入成绩行（首次被观测时惰性执行，async 上下文才有会话）。"""
    if _state["status"] != "done" or _state["result_id"] is not None or _state["device"] is None:
        return
    curve = _state["curve"]
    total_t = _state["elapsed"] or 1e-6
    row = BenchResult(
        device=_state["device"][:24],
        seconds=_state["seconds"],
        duty=_state["duty"],
        avg_mbps=round(_state["bytes_read"] / total_t / 1048576, 1),  # 墙钟均值（含限速窗口）
        peak_mbps=round(max((p["mbps"] for p in curve), default=0.0), 1),
        bytes_read=_state["bytes_read"],
        direct=_state["direct"],
        curve=curve,
    )
    db.add(row)
    await db.flush()
    _state["result_id"] = row.id


async def history(db: AsyncSession, device: str | None = None, limit: int = 100) -> list[dict]:
    """成绩榜（新→旧）；device 过滤做同盘历史对比。"""
    await maybe_persist(db)
    stmt = select(BenchResult).order_by(BenchResult.id.desc()).limit(min(limit, 500))
    if device:
        stmt = stmt.where(BenchResult.device == device)
    result = await db.execute(stmt)
    return [
        {
            "id": r.id,
            "device": r.device,
            "seconds": r.seconds,
            "duty": r.duty,
            "avg_mbps": r.avg_mbps,
            "peak_mbps": r.peak_mbps,
            "bytes_read": r.bytes_read,
            "direct": r.direct,
            "created_at": r.created_at,
            "curve": r.curve or [],
        }
        for r in result.scalars()
    ]


# ---------------------------------------------------------------- worker（线程）

def _open_direct(device: str) -> tuple[int, mmap.mmap, memoryview]:
    """O_DIRECT 打开块设备 + 页对齐读缓冲（O_DIRECT 要求缓冲/长度/偏移扇区对齐）。

    Raises:
        ExternalToolError: 非 Linux / O_DIRECT 打开失败（含内核不支持）。
    """
    try:
        fd = os.open(f"/dev/{device}", os.O_RDONLY | getattr(os, "O_DIRECT", 0))
    except OSError as exc:
        raise ExternalToolError(f"O_DIRECT 打开 /dev/{device} 失败：{exc}") from exc
    buf = mmap.mmap(-1, BLK)  # mmap 页对齐，满足 O_DIRECT 缓冲对齐要求
    return fd, buf, memoryview(buf)


def _worker(device: str, seconds: int, duty: int) -> None:
    """基准主体（独立线程，不占事件循环）：顺序读 + 占空比限速 + 采样。"""
    fd = None
    buf = view = None
    try:
        fd, buf, view = _open_direct(device)
        _state["direct"] = True
        total_size = os.lseek(fd, 0, os.SEEK_END)  # 块设备字节数
        t0 = time.monotonic()
        deadline = t0 + seconds
        offset = 0

        while time.monotonic() < deadline and not _state["stop"]:
            win_t0 = time.monotonic()
            win_active = SAMPLE_WIN * duty / 100.0
            win_bytes = 0
            # 工作窗：读到占满 duty 比例的窗口
            while time.monotonic() - win_t0 < win_active and time.monotonic() < deadline:
                if offset >= total_size:
                    offset = 0  # 盘尾回卷：顺序读从头再来（窗口定总时长）
                n = os.preadv(fd, [view[:BLK]], offset)
                if n <= 0:
                    break
                offset += n
                win_bytes += n
            # 休眠窗：把窗口剩余时间让给业务 IO（占空比限速核心）
            rest = win_t0 + SAMPLE_WIN - time.monotonic()
            if rest > 0:
                time.sleep(rest)

            now = time.monotonic()
            _state["bytes_read"] += win_bytes
            _state["elapsed"] = now - t0
            _state["progress"] = min(100.0, (now - t0) / seconds * 100)
            mbps = round(win_bytes / SAMPLE_WIN / 1048576, 1)  # 窗口吞吐（含休眠，真实业务视角）
            _state["bps"] = mbps * 1048576
            if len(_state["curve"]) < CURVE_CAP:
                _state["curve"].append({"t": round(now - t0, 1), "mbps": mbps})

        _state["elapsed"] = time.monotonic() - t0
        _state["progress"] = 100.0
        _state["status"] = "done"  # 取消同样记成绩（部分数据有效）
    except Exception as exc:  # noqa: BLE001 worker 独立线程：异常落状态机
        _state["status"] = "error"
        _state["error"] = str(exc)[:300]
    finally:
        if fd is not None:
            os.close(fd)
        try:
            if view is not None:
                view.release()  # memoryview 须先于 mmap 释放
            if buf is not None:
                buf.close()
        except (BufferError, ValueError):
            pass
