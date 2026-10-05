"""阵列管理：storcli 硬 RAID（Broadcom/LSI MegaRAID）+ /proc/mdstat 软 RAID（契约 §2.8）。

storcli 文本解析在 storcli.py（移植旧版实测实现）；本模块负责：
- 阻塞调用包线程池（storcli 一轮可能 0.3-30s）；
- storcli 结果 → 契约 RaidVolumeItem / controller / drives 形状；
- storcli 不可用时 hardware_raid 置空、available=false，软 RAID 照常返回。
"""

from __future__ import annotations

import asyncio
import re

from app.services.storage import storcli
from app.utils.async_cmd import run_cmd
from app.utils.sysfs import read_text


async def raid_status() -> dict:
    """聚合硬 RAID（storcli）与软 RAID（/proc/mdstat）状态。

    storcli 探测失败不阻断软 RAID：hardware_raid 置空、available=false、错误落
    storcli_error；storcli 无 MegaRAID 可报时回退 lspci 检测 HBA 直通卡。

    Returns:
        dict: {available, hardware_raid, software_raid, storcli_error, controller, drives}，
            形状对齐契约 RaidVolumeItem / controller / drives。
    """
    software = _mdstat_volumes()
    storcli_error = None
    card = None
    try:
        card = await asyncio.to_thread(storcli.collect, _storcli_text_run)
    except Exception as exc:  # noqa: BLE001 storcli 探测失败不阻断软 RAID
        storcli_error = str(exc)

    hardware: list[dict] = []
    drives = (card or {}).get("drives", [])
    if card and card.get("ok") and card.get("virtual_drives"):
        # PD 表只带 DG 列：DG 内多 VD 时物理盘无法唯一归属，此时不挂成员（宁缺勿错边）
        dg_counts: dict[str, int] = {}
        for vd in card["virtual_drives"]:
            dgvd = vd.get("dgvd", "")
            if "/" in dgvd:
                dg_counts[dgvd.split("/")[0]] = dg_counts.get(dgvd.split("/")[0], 0) + 1
        for vd in card["virtual_drives"]:
            dgvd = vd.get("dgvd", "")
            dg = dgvd.split("/")[0] if "/" in dgvd else None
            unambiguous = dg is not None and dg_counts.get(dg, 0) == 1
            hardware.append(
                {
                    "source": "storcli",
                    "controller": (dgvd.split("/")[0] if "/" in dgvd else "0"),
                    "volume_id": (dgvd.split("/")[1] if "/" in dgvd else dgvd),
                    "name": vd.get("name") or f"VD {dgvd}",
                    "level": _norm_level(vd.get("type", "")),
                    "size_bytes": storcli.size_to_bytes(vd.get("size", "")) if vd.get("size") else None,
                    "state": vd.get("state", ""),
                    "healthy": vd.get("state") == "Optl",
                    # PD↔VD 靠 DG 编号 join（storcli 拓扑表唯一可用关联）；专用热备
                    # DG 同号会一并挂入并以 hotspare 标记，全局热备 DG="-" 不挂
                    "members": [
                        {
                            "slot": d.get("slot"),
                            "sn": d.get("sn") or None,
                            "model": d.get("model") or None,
                            "state": d.get("state"),
                            "media": d.get("media"),
                            "size_human": d.get("size"),
                            "hotspare": d.get("hotspare"),
                            "failed": bool(d.get("failed")),
                        }
                        for d in drives
                        if unambiguous and str(d.get("dg")) == dg
                    ],
                    "details": {
                        "consist": vd.get("consist", ""),
                        "cache_raw": vd.get("cache_raw", ""),
                        "write_policy": vd.get("write_policy", ""),
                        "read_policy": vd.get("read_policy", ""),
                        "read_cache": vd.get("read_cache", ""),
                        "size_human": vd.get("size", ""),
                    },
                }
            )
    elif card and card.get("note"):
        storcli_error = storcli_error or card["note"]

    controller = (card or {}).get("controller")
    # storcli 无 MegaRAID 可报时，回退 lspci 检测 HBA 直通卡（如 LSI SAS2308 IT 模式）
    if not (card and card.get("ok")):
        hba = await _detect_hba()
        if hba:
            controller = hba
            storcli_error = storcli.HBA_NOTE

    return {
        "available": storcli_error is None and bool(card and card.get("ok")),
        "hardware_raid": hardware,
        "software_raid": software,
        "storcli_error": storcli_error,
        "controller": controller,
        "drives": drives,
    }


async def _detect_hba() -> dict | None:
    """lspci 只读检测 HBA 直通卡；附带 mpt3sas 驱动版本（真机 fnOS 1.2 实测可读）。

    lspci 在位与否由策略决策层启动时判定（policy.tools），缺失直接跳过不 fork。

    Returns:
        dict | None: {mode, model, driver, note}；无 lspci、命令失败或无 HBA 时返回 None。
    """
    from app.services.hardware.policy import get_policy

    if not get_policy().tools.get("lspci"):
        return None
    try:
        _rc, out, _err = await run_cmd("lspci", "-nn", timeout=10)
    except Exception:  # noqa: BLE001
        return None
    hba = [c for c in storcli.detect_controllers(out) if c["is_hba"]]
    if not hba:
        return None
    from app.utils.sysfs import read_text

    return {
        "mode": "hba",
        "model": hba[0]["model"],
        "driver": f"mpt3sas {read_text('/sys/module/mpt3sas/version') or ''}".strip(),
        "note": storcli.HBA_NOTE,
    }


def _norm_level(storcli_type: str) -> str:
    """storcli TYPE 列（RAID5/RAID10/JBOD...）→ 常规级别文本。

    Args:
        storcli_type (str): storcli 拓扑表 TYPE 列原文。

    Returns:
        str: RAID 前缀剥离后的级别（如 "5"、"10"）；非 RAID 型号原样返回，空值归 "unknown"。
    """
    t = (storcli_type or "").upper()
    if t.startswith("RAID"):
        return t.removeprefix("RAID")
    return storcli_type or "unknown"


def _storcli_text_run(args: list[str], timeout: float) -> str:
    """storcli.collect 的同步执行器（运行于 to_thread 工作线程，不可 await）。

    Args:
        args (list[str]): storcli 参数列表（不含可执行名）。
        timeout (float): 命令超时秒数。

    Returns:
        str: storcli 标准输出。

    Raises:
        RuntimeError: 返回码非 0 且无输出（错误信息截断至 120 字符）。
    """
    from app.utils.async_cmd import run_storcli_sync

    rc, out, err = run_storcli_sync(*args, timeout=timeout)
    if rc != 0 and not out:
        raise RuntimeError(f"storcli rc={rc}: {err.strip()[:120]}")
    return out


_MD_MEMBER = re.compile(r"(\S+)\[(\d+)\](\([A-Z]+\))?")

# 同步进度行："[=====>...]  resync = 62.3% (1823/2930) finish=123.4min speed=148736K/sec"
_MD_SYNC = re.compile(
    r"(resync|recovery|rebuild|check|reshape)\s*=\s*"
    r"(?:(\d+(?:\.\d+)?)%\s*\(\d+/\d+\)\s*)?"
    r"(?:finish=\s*([\d.]+)(min|sec)\s*)?"
    r"(?:speed=\s*(\d+)\s*([KMG])/sec)?"
)


def _md_sync_info(lines: list[str], start: int) -> dict | None:
    """blocks 行向下扫描本 md 的同步段（M2.4）。

    Args:
        lines (list[str]): /proc/mdstat 全部行。
        start (int): 本 md 成员行下标，自其后开始扫描。

    Returns:
        dict | None: 同步进行中返回 {action, percent, finish_text, speed_text}
            （delayed 无百分比）；无同步活动返回 None。
    """
    for follow in lines[start + 1 : start + 6]:
        match = _MD_SYNC.search(follow)
        if match:
            action, pct, finish, unit, speed, speed_unit = match.groups()
            info: dict = {"action": action, "percent": float(pct) if pct else None}
            if finish:
                info["finish_text"] = f"{finish}{unit}"
            if speed:
                info["speed_text"] = f"{speed}{speed_unit}/s"
            return info
        if follow.startswith("md") or not follow.strip():
            break  # 进入下一个 md 或空行段：本 md 无同步活动
    return None


def _md_members(rest: str) -> list[dict]:
    """解析 mdstat 成员段（"sda2[0] sdb2[1](F)"）→ 结构化成员。

    Args:
        rest (str): mdstat 成员行 " : " 之后的原文。

    Returns:
        list[dict]: 每项 {device, index, faulty, spare}（faulty/spare 按括号标记 F/S 判定）。
    """
    members = []
    for match in _MD_MEMBER.finditer(rest):
        device, index, flag = match.group(1), int(match.group(2)), match.group(3) or ""
        members.append(
            {
                "device": device,
                "index": index,
                "faulty": "(F" in flag,
                "spare": "(S" in flag,
            }
        )
    return members


def _mdstat_volumes(path: str = "/proc/mdstat") -> list[dict]:
    """解析 /proc/mdstat → 软 RAID 卷列表（契约 RaidVolumeItem 形状，source=mdadm）。

    Args:
        path (str): mdstat 路径（默认 "/proc/mdstat"，测试可注入）。

    Returns:
        list[dict]: 每卷 {source, controller, volume_id, name, level, size_bytes, state,
            healthy, members, details}；文件为空或不含活动阵列返回 []。
    """
    text = read_text(path)
    if not text:
        return []
    volumes = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if " : active" not in line:
            continue
        name, rest = line.split(" : ", 1)
        parts = rest.split()
        level = parts[1].lstrip("raid") if len(parts) > 1 else "unknown"
        # 成员行下一行形如 "8790400320 blocks super 1.2 ... [4/4] [UUUU]"：
        # blocks 单位 KiB；盘位状态 [U_U] 在该行，降级判断须连同它一起看
        size_bytes = None
        blocks_line = ""
        for follow in lines[i + 1 : i + 3]:
            match = re.search(r"(\d+) blocks", follow)
            if match:
                size_bytes = int(match.group(1)) * 1024
                blocks_line = follow
                break
        healthy = "_" not in rest and "_" not in blocks_line
        # 同步段从成员行之后扫起（进度行通常紧跟 blocks 行；窗口 5 行覆盖 bitmap 夹层）
        sync = _md_sync_info(lines, i + 1)
        details: dict = {"members": rest[:200]}
        if sync:
            details["sync"] = sync
        volumes.append(
            {
                "source": "mdadm",
                "controller": "soft",
                "volume_id": name,
                "name": name,
                "level": level,
                "size_bytes": size_bytes,
                "state": "clean" if healthy else "degraded",
                "healthy": healthy,
                "members": _md_members(rest),
                "details": details,
            }
        )
    return volumes
