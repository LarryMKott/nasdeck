"""容器退出检测（M2.3）：对比前后两轮 docker ps -a 状态，running→非 running 即告警。

nasdeck 无容器 stop 接口，任何退出均视为意外（手动 docker stop 也会告警——
属已知行为）。每容器 1 小时去重窗抑制重启风暴；首轮只建基线不告警（避免
启动/升级窗口对存量退出容器轰炸）。60 秒一拍由 slow_60s 驱动。
"""

from __future__ import annotations

import logging
import time

from app.services.system import docker

logger = logging.getLogger(__name__)

DEDUP_SECONDS = 3600
_prev_states: dict[str, str] = {}  # cid → state（仅上一轮）
_last_alert: dict[str, float] = {}  # cid → 最近告警 monotonic 时刻


def reset_for_test() -> None:
    """清空进程内状态（上一轮状态基线与去重时刻表），仅供测试隔离。"""
    _prev_states.clear()
    _last_alert.clear()


async def watch_tick() -> list[dict]:
    """一轮状态对比（60 秒一拍，slow_60s 驱动），返回本拍需告警的退出事件。

    首轮只建基线不告警（避免启动/升级窗口对存量退出容器轰炸）；
    消失的容器（被删除）一并清出基线。

    Returns:
        list[dict]: 退出事件列表，每项 {cid, name, status}；docker
        不可用时为空列表。
    """
    states = await docker.list_all_states()
    if states is None:
        return []
    now = time.monotonic()
    events = []
    for cid, info in states.items():
        prev = _prev_states.get(cid)
        if prev == "running" and info["state"] not in ("running", "restarting"):
            if now - _last_alert.get(cid, float("-inf")) >= DEDUP_SECONDS:
                _last_alert[cid] = now
                events.append({"cid": cid, "name": info["name"], "status": info["status"]})
    # 基线更新：消失的容器（被删除）一并清出
    for cid in list(_prev_states):
        if cid not in states:
            _prev_states.pop(cid, None)
    for cid, info in states.items():
        _prev_states[cid] = info["state"]
    return events


async def persist_and_notify(db, exits: list[dict]) -> None:
    """退出事件落事件历史（一次性 resolved 记录）并向全部启用渠道广播。

    Args:
        db (AsyncSession): 请求级会话（调用方负责 commit）。
        exits (list[dict]): watch_tick 返回的退出事件，每项含 cid/name/status。
    """
    from datetime import UTC, datetime

    from app.models.alert import AlertEvent
    from app.services.alert import engine as alert_engine

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    for e in exits:
        message = f"容器 {e['name']} 意外退出（{e['status']}）"
        db.add(
            AlertEvent(
                rule_id=None,
                rule_name="容器退出",
                metric="docker_exit",
                value=None,
                threshold=None,
                severity="warning",
                status="resolved",
                message=message,
                fired_at=now,
                resolved_at=now,
            )
        )
        await alert_engine.notify_broadcast(db, title=f"容器退出 · {e['name']}", body=message)
    await db.flush()
