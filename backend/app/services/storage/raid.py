"""阵列管理：storcli 硬 RAID（Broadcom/LSI MegaRAID）+ /proc/mdstat 软 RAID（契约 §2.8）。

storcli 文本解析在 storcli.py（移植旧版实测实现）；本模块负责：
- 阻塞调用包线程池（storcli 一轮可能 0.3-30s）；
- storcli 结果 → 契约 RaidVolumeItem / controller / drives 形状；
- storcli 不可用时 hardware_raid 置空、available=false，软 RAID 照常返回。
"""

from __future__ import annotations

import asyncio

from app.services.storage import storcli
from app.utils.async_cmd import run_cmd
from app.utils.sysfs import read_text


async def raid_status() -> dict:
    software = _mdstat_volumes()
    storcli_error = None
    card = None
    try:
        card = await asyncio.to_thread(storcli.collect, _storcli_text_run)
    except Exception as exc:  # noqa: BLE001 storcli 探测失败不阻断软 RAID
        storcli_error = str(exc)

    hardware: list[dict] = []
    if card and card.get("ok") and card.get("virtual_drives"):
        for vd in card["virtual_drives"]:
            dgvd = vd.get("dgvd", "")
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
        "drives": (card or {}).get("drives", []),
    }


async def _detect_hba() -> dict | None:
    """lspci 只读检测 HBA 直通卡；附带 mpt3sas 驱动版本（真机 fnOS 1.2 实测可读）。"""
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
    """storcli TYPE 列（RAID5/RAID10/JBOD...）→ 常规级别文本。"""
    t = (storcli_type or "").upper()
    if t.startswith("RAID"):
        return t.removeprefix("RAID")
    return storcli_type or "unknown"


def _storcli_text_run(args: list[str], timeout: float) -> str:
    """storcli.collect 的同步执行器（运行于 to_thread 工作线程，不可 await）。"""
    from app.utils.async_cmd import run_storcli_sync

    rc, out, err = run_storcli_sync(*args, timeout=timeout)
    if rc != 0 and not out:
        raise RuntimeError(f"storcli rc={rc}: {err.strip()[:120]}")
    return out


def _mdstat_volumes() -> list[dict]:
    text = read_text("/proc/mdstat")
    if not text:
        return []
    volumes = []
    for line in text.splitlines():
        if " : active" not in line:
            continue
        name, rest = line.split(" : ", 1)
        parts = rest.split()
        level = parts[1].lstrip("raid") if len(parts) > 1 else "unknown"
        healthy = "[UU]" in rest or "_" not in rest
        volumes.append(
            {
                "source": "mdadm",
                "controller": "soft",
                "volume_id": name,
                "name": name,
                "level": level,
                "size_bytes": None,
                "state": "clean" if healthy else "degraded",
                "healthy": healthy,
                "details": {"members": rest[:200]},
            }
        )
    return volumes
