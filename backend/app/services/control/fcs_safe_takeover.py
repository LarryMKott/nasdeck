"""飞牛 FCS 安全接管：停原生 pwm-fancontrol、交还时恢复（契约 §2.18）。

非 fnOS / 非 Linux 环境所有操作返回 reason，不抛错（安全第一）。
接管状态落盘 data/fcs_state.json：进程被 SIGKILL（升级停机是常规操作）后
重启仍能如实上报，避免 status() 谎报未接管、原生 FCS 实际仍被禁用。
"""

from __future__ import annotations

import json
import logging
import platform

from app.core.config import APP_ROOT
from app.utils.async_cmd import run_cmd
from app.utils.sysfs import read_text

logger = logging.getLogger(__name__)

UNIT = "pwm-fancontrol"

_STATE_FILE = APP_ROOT / "data" / "fcs_state.json"
_state = {"taken_over": False, "enabled_config": False}


def is_fnos() -> bool:
    return read_text("/usr/trim/etc/version") is not None


def load_state() -> None:
    """启动时从落盘状态对账（幂等）：崩溃/升级重启后 taken_over 依旧如实。"""
    try:
        data = json.loads(_STATE_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return  # 无状态文件：从未接管过（或开发机）
    _state["taken_over"] = bool(data.get("taken_over"))
    _state["enabled_config"] = bool(data.get("enabled_config"))
    if _state["taken_over"]:
        logger.warning("检测到未归还的 FCS 接管状态：原生 %s 仍处于禁用，受管控区将按配置恢复调速", UNIT)


def _persist_state() -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(_state), "utf-8")
    except OSError as exc:
        logger.warning("FCS 接管状态落盘失败: %s", exc)


async def status() -> dict:
    active: bool | None = None
    if platform.system() == "Linux" and is_fnos():
        try:
            rc, _out, _err = await run_cmd("systemctl", "is-active", "--quiet", UNIT, timeout=5)
            active = rc == 0
        except Exception:
            active = None
    return {
        "is_fnos": is_fnos(),
        "unit": UNIT,
        "active": active,
        "taken_over": _state["taken_over"],
        "enabled_config": _state["enabled_config"],
    }


async def takeover() -> dict:
    if not is_fnos():
        return {"taken_over": False, "reason": "非 fnOS 环境，无需接管"}
    if platform.system() != "Linux":
        return {"taken_over": False, "reason": "非 Linux 环境不可执行 systemctl"}
    try:
        # run_cmd 非零退出不抛异常（只超时/命令缺失才抛），必须逐条检查 rc，
        # 否则 stop/disable 失败仍会置 taken_over=True（审查 2026-09-30 P1）
        rc, _out, err = await run_cmd("systemctl", "stop", UNIT, timeout=10)
        if rc != 0:
            return {"taken_over": False, "reason": f"systemctl stop 失败 rc={rc}: {err.strip()[:150]}"}
        rc, _out, err = await run_cmd("systemctl", "disable", UNIT, timeout=10)
        if rc != 0:
            return {"taken_over": False, "reason": f"systemctl disable 失败 rc={rc}: {err.strip()[:150]}"}
    except Exception as exc:
        return {"taken_over": False, "reason": str(exc)[:200]}
    _state["taken_over"] = True
    _state["enabled_config"] = True
    _persist_state()
    return {"taken_over": True}


async def release() -> dict:
    if not is_fnos():
        return {"released": False, "reason": "非 fnOS 环境，无需恢复"}
    if platform.system() != "Linux":
        return {"released": False, "reason": "非 Linux 环境不可执行 systemctl"}
    try:
        # 须等待 systemctl 完成并确认成功后才翻转状态（原实现只创建子进程不等待）
        rc, _out, err = await run_cmd("systemctl", "enable", "--now", UNIT, timeout=15)
        if rc != 0:
            return {"released": False, "reason": f"systemctl enable --now 失败 rc={rc}: {err.strip()[:150]}"}
    except Exception as exc:
        return {"released": False, "reason": str(exc)[:200]}
    _state["taken_over"] = False
    _state["enabled_config"] = False
    _persist_state()
    return {"released": True}
