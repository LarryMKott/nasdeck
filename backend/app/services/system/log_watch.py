"""系统日志哨兵（M3.4）：低频扫描内核日志，正则聚合关键错误并告警。

盘出问题前 dmesg 往往先报（I/O error 常早于 SMART 计数增长），本哨兵补上
这条更早的信号链。数据源 `journalctl -k -n 300`（Linux only，5 分钟一拍），
逐行匹配关键错误正则，命中 → 事件历史 + 全渠道广播；按行内容哈希 24h 去重。
非 Linux / journalctl 缺失 / 命令失败一律静默返回空（不告警不报错）。
"""

from __future__ import annotations

import hashlib
import logging
import platform
import re
import time

from app.utils.async_cmd import run_cmd

logger = logging.getLogger(__name__)

# 关键错误正则（不区分大小写；前半是症状关键词，后半补上下文定位信息）
_PATTERNS = (
    re.compile(r"(?:I/O error|blk_update_request)", re.I),
    re.compile(r"(?:uncorrectable|pending) sector", re.I),
    re.compile(r"\bECC\b.*(?:error|corrected)", re.I),
    re.compile(r"throttl|over temperatur", re.I),
    re.compile(r"SMART overall-health.*(?:FAILED|failing)", re.I),
    re.compile(r"segfault|general protection", re.I),
    re.compile(r"Out of memory: Killed process", re.I),
    re.compile(r"md/raid.*(?:not enough operational|reshape|resync.*abort)", re.I),
)

DEDUP_SECONDS = 24 * 3600
_seen_hashes: dict[str, float] = {}
TAIL_LINES = 300


def reset_for_test() -> None:
    _seen_hashes.clear()


def match_lines(lines: list[str]) -> list[dict]:
    """日志行过滤为命中条目（按 24h 去重窗）。

    Args:
        lines (list[str]): journalctl 输出行。

    Returns:
        list[dict]: 命中行 [{hash, line}]（去重后）。
    """
    now = time.monotonic()
    out = []
    for line in lines:
        if not any(p.search(line) for p in _PATTERNS):
            continue
        digest = hashlib.sha1(line.encode("utf-8", "replace")).hexdigest()[:16]
        if now - _seen_hashes.get(digest, float("-inf")) < DEDUP_SECONDS:
            continue
        _seen_hashes[digest] = now
        out.append({"hash": digest, "line": line[:200]})
    # 哈希表防膨胀：只留 24h 窗内的
    for digest in [k for k, ts in _seen_hashes.items() if now - ts >= DEDUP_SECONDS]:
        _seen_hashes.pop(digest, None)
    return out


async def watch_tick() -> list[dict]:
    """一轮内核日志扫描，返回命中事件 [{hash, line}]（平台不支持返回空）。"""
    if platform.system() != "Linux":
        return []
    try:
        _rc, out, _err = await run_cmd("journalctl", "-k", "-n", str(TAIL_LINES), "--no-pager", timeout=30)
    except Exception:  # noqa: BLE001 journalctl 缺失/无权限：静默跳过
        return []
    return match_lines(out.splitlines())


async def persist_and_notify(db, events: list[dict]) -> None:
    """命中事件落事件历史并向全部启用渠道广播。调用方负责 commit。

    Args:
        db: 任务级会话。
        events (list[dict]): watch_tick 输出。
    """
    from datetime import UTC, datetime

    from app.models.alert import AlertEvent
    from app.services.alert import engine as alert_engine

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    for e in events:
        db.add(
            AlertEvent(
                rule_id=None,
                rule_name="日志哨兵",
                metric="log_alert",
                value=None,
                threshold=None,
                severity="warning",
                status="resolved",
                message=e["line"],
                fired_at=now,
                resolved_at=now,
            )
        )
        await alert_engine.notify_broadcast(db, title="日志哨兵 · 内核关键错误", body=e["line"])
    await db.flush()
