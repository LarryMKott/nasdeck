"""阵列同步活动监视（M2.4）：对比前后两轮 mdstat 同步段，开始/结束写事件历史。

开始（warning，向启用渠道广播——同步多由降级重建引发）与结束（info，仅事件）
均落 resolved 一次性记录，与容器退出/巡检同一形态。60 秒一拍由 slow_60s 驱动；
storcli VD 的 Rbld 状态文本本就随 state 字段透出，不在此重复检测。
"""

from __future__ import annotations

import logging

from app.services.storage import raid as raid_service

logger = logging.getLogger(__name__)

_prev_sync: dict[str, str] = {}  # volume_id → action（无活动不占键）


def reset_for_test() -> None:
    """清空进程内前次同步状态表（测试隔离用）。"""
    _prev_sync.clear()


async def detect_sync_transitions() -> list[dict]:
    """一轮对比，产出同步开始/结束转换事件。

    探测失败跳过本轮（不产生伪转换）；开始/结束事件均由调用方落 resolved
    一次性记录并向启用渠道广播。

    Returns:
        list[dict]: [{volume_id, name, phase: 'started'|'finished', action}]。
    """
    try:
        raids = await raid_service.raid_status()
    except Exception as exc:  # noqa: BLE001 探测失败跳过本轮（不产生伪转换）
        logger.debug("raid_status 失败，跳过同步检测: %s", exc)
        return []
    current: dict[str, dict] = {}
    for vol in raids.get("software_raid", []):
        sync = (vol.get("details") or {}).get("sync")
        if sync and vol.get("volume_id"):
            current[vol["volume_id"]] = {"name": vol.get("name") or vol["volume_id"], **sync}

    events = []
    for vid, sync in current.items():
        if vid not in _prev_sync:
            events.append({"volume_id": vid, "name": sync["name"], "phase": "started", "action": sync["action"]})
        _prev_sync[vid] = sync["action"]
    for vid in list(_prev_sync):
        if vid not in current:  # 同步段消失 = 完成/中止
            action = _prev_sync.pop(vid)
            events.append({"volume_id": vid, "name": vid, "phase": "finished", "action": action})
    return events
