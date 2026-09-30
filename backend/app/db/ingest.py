"""采集数据落库通道：单写者 + 攒批批量插入。

周期采集（fast/slow tick）的纯插入数据统一投递本通道：
- 单一消费者持有专用连接（aiosqlite 每连接绑定一个工作线程），SQLite 层
  不再有多任务抢写锁——竞争在通道入口（内存队列）即被串行化；
- 攒批（条数或时间阈值先到为准）executemany 一次落盘，把 fsync 摊到多条数据；
- 队列满（盘持续过慢）丢新数据并限频记日志：采集数据流宁丢不堵调度。

API 层需同步返回 id 的写（规则/别名/设置 CRUD）与含读改写的事务
（medium_tick 温度回填、downsampler 聚合）不经此通道，维持原事务路径。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.session import session_factory
from app.models.hardware import HardwareItem
from app.models.metrics import MetricPoint

logger = logging.getLogger(__name__)

_BATCH_MAX = 50  # 攒批条数上限（任一表攒够即落盘）
_FLUSH_INTERVAL = 2.0  # 攒批时长上限（秒）
_QUEUE_MAX = 600  # 队列积压上限（≈10 分钟采集量），满则丢弃

_tables = {"metrics": MetricPoint, "hardware": HardwareItem}


def _stmt(kind: str):
    stmt = sqlite_insert(_tables[kind])
    if kind == "metrics":
        stmt = stmt.on_conflict_do_nothing(index_elements=["ts", "granularity"])
    return stmt


_queue: asyncio.Queue | None = None
_task: asyncio.Task | None = None
_dropped_since_log = 0


def submit(kind: str, row: dict) -> None:
    """非阻塞投递一行采集数据；队列满丢弃（容灾，不阻塞采集调度）。"""
    global _dropped_since_log
    if _queue is None:  # worker 未启动（如单测直调采集函数）——静默丢弃
        return
    try:
        _queue.put_nowait((kind, row))
        _dropped_since_log = 0
    except asyncio.QueueFull:
        _dropped_since_log += 1
        if _dropped_since_log <= 1 or _dropped_since_log % 60 == 0:  # 限频防刷屏
            logger.warning("ingest 队列已满，累计丢弃 %d 行（盘写入持续过慢）", _dropped_since_log)


async def _write(pending: dict[str, list[dict]]) -> None:
    rows_total = sum(len(rows) for rows in pending.values())
    if not rows_total:
        return
    try:
        async with session_factory() as db:
            for kind, rows in pending.items():
                if rows:
                    await db.execute(_stmt(kind), rows)  # executemany 批量
            await db.commit()
    except Exception as exc:  # noqa: BLE001 落库失败不拖垮采集
        logger.warning("ingest 批量落库失败（丢弃 %d 行）: %s", rows_total, exc)


async def _run() -> None:
    pending: dict[str, list[dict]] = {kind: [] for kind in _tables}
    last_flush = time.monotonic()
    while True:
        timeout = max(0.0, _FLUSH_INTERVAL - (time.monotonic() - last_flush))
        try:
            kind, row = await asyncio.wait_for(_queue.get(), timeout=timeout)
            pending[kind].append(row)
        except TimeoutError:  # asyncio.TimeoutError 的 3.11+ 别名
            pass
        due = time.monotonic() - last_flush >= _FLUSH_INTERVAL
        full = any(len(rows) >= _BATCH_MAX for rows in pending.values())
        if due or full:
            await _write(pending)
            pending = {kind: [] for kind in _tables}
            last_flush = time.monotonic()


def start() -> None:
    """启动落库 worker（须在事件循环内调用，lifespan 里执行）。"""
    global _queue, _task
    if _task is None:
        _queue = asyncio.Queue(maxsize=_QUEUE_MAX)
        _task = asyncio.create_task(_run(), name="ingest-writer")


async def stop() -> None:
    global _queue, _task
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None
    _queue = None  # 残留队列数据随 worker 终止丢弃（采集流，可丢）


def _reset_for_test() -> None:
    global _queue, _task, _dropped_since_log
    _queue, _task, _dropped_since_log = None, None, 0
