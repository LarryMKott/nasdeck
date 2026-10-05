"""Broadcom/LSI MegaRAID（storcli）文本输出解析与采集。

解析逻辑移植自旧版 v2.3.x 实测实现（prototype 备份 backend/infrastructure/collectors/raid.py），
保留其中的实战修复：
- VD 拓扑表分隔线夹在表头与数据行之间（v2.3.2），分隔线只跳过、遇实质行才结束；
- PD 型号从行尾反向定位（Size 恒 2 token、SeSz 1-2 token 导致固定下标错位），
  型号/序列号/温度优先来自 `/c0/eall/sall show all` 的键值对（一条命令拿全盘）；
- CacheVault/BBU 多格式兼容；ROC 与 Controller 是两个物理温度传感器，分开解析；
- storcli 把二进制 TiB/GiB 误标为 TB/GB，容量换算回十进制显示。

执行器注入（run(args, timeout) -> str）便于测试桩替身；Windows/无卡环境全部降级。
"""

from __future__ import annotations

import re
import threading
import time

_TTL = 15
_cache: dict = {"ts": 0.0, "data": None}
_lock = threading.Lock()

_KNOWN_VENDORS = (
    "ST", "WD", "WDC", "TOSHIBA", "HGST", "HUH", "HUS", "INTEL", "KINGSTON",
    "CT", "CRUCIAL", "MICRON", "SANDISK", "PNY", "HITACHI", "SAMSUNG",
)


def size_to_decimal(size_str: str) -> str:
    """storcli 的 TB/GB 实为 TiB/GiB，换算回十进制显示（6.366 TB → 7.0T）。

    Args:
        size_str (str): storcli 容量文本（如 "6.366 TB"）。

    Returns:
        str: 十进制显示串（≥1TB 取 "7.0T" 形态，否则 "931G"）；不匹配或解析失败原样返回。
    """
    try:
        m = re.match(r"^([\d.]+)\s*(TB|GB|MB)$", size_str.strip(), re.I)
        if not m:
            return size_str
        num = float(m.group(1))
        unit = m.group(2).upper()
        bytes_ = num * (1024**4 if unit == "TB" else 1024**3 if unit == "GB" else 1024**2)
        if bytes_ / 1e12 >= 1:
            return f"{bytes_ / 1e12:.1f}T"
        return f"{bytes_ / 1e9:.0f}G"
    except Exception:
        return size_str


def size_to_bytes(size_str: str) -> int | None:
    """storcli 容量文本 → 十进制字节数。

    Args:
        size_str (str): storcli 容量文本（如 "6.366 TB"）。

    Returns:
        int | None: 字节数；None 表示解析失败。
    """
    try:
        m = re.match(r"^([\d.]+)\s*(TB|GB|MB)$", size_str.strip(), re.I)
        if not m:
            return None
        num = float(m.group(1))
        unit = m.group(2).upper()
        return int(num * (1024**4 if unit == "TB" else 1024**3 if unit == "GB" else 1024**2))
    except Exception:
        return None


def resolve_brand_model(tbl_model: str, inquiry_model: str) -> str:
    """表格型号常丢厂商前缀，品牌识别优先用含前缀的完整型号（旧版 v1.7.8 修复）。

    Args:
        tbl_model (str): PD LIST 表格列型号。
        inquiry_model (str): show all 键值对的 Inquiry 型号。

    Returns:
        str: 表格型号无厂商前缀且 Inquiry 型号有时取 inquiry_model，否则 tbl_model。
    """
    if not inquiry_model or inquiry_model == "-":
        return tbl_model
    tbl_vendor = tbl_model.upper().startswith(_KNOWN_VENDORS) or "SAMSUNG" in tbl_model.upper()
    inq_vendor = inquiry_model.upper().startswith(_KNOWN_VENDORS) or "SAMSUNG" in inquiry_model.upper()
    return inquiry_model if (not tbl_vendor and inq_vendor) else tbl_model


def disk_brand(model: str) -> str:
    """型号 → 中文品牌（无法识别返回空串）。

    Args:
        model (str): 硬盘型号。

    Returns:
        str: 中文品牌（如 "希捷(Seagate)"）；无法识别返回空串。
    """
    model_u = (model or "").strip().upper()
    table = (
        (("ST",), "希捷(Seagate)"),
        (("WD", "WDC"), "西部数据(WD)"),
        (("HGST", "HUH", "HUS"), "HGST(日立)"),
        (("INTEL",), "英特尔(Intel)"),
        (("KINGSTON",), "金士顿(Kingston)"),
        (("CT", "CRUCIAL"), "英睿达(Crucial)"),
        (("PNY",), "PNY"),
    )
    for prefixes, brand in table:
        if model_u.startswith(prefixes):
            return brand
    for needle, brand in (
        ("TOSHIBA", "东芝(Toshiba)"),
        ("SAMSUNG", "三星(Samsung)"),
        ("MICRON", "美光(Micron)"),
        ("SANDISK", "闪迪(SanDisk)"),
        ("HITACHI", "日立(Hitachi)"),
    ):
        if needle in model_u:
            return brand
    return ""


def parse_roc_temp(text: str | None) -> int | None:
    """解析 ROC（主控芯片）温度，兼容 `ROC temperature = 56` 与 `ROC temperature(Degree Celsius) 65`。

    Args:
        text (str | None): storcli 文本输出。

    Returns:
        int | None: 温度（℃）；未匹配或入参为空返回 None。
    """
    if not text:
        return None
    m = re.search(r"ROC\s+temperature\s*(?:\([^)]*\))?\s*=?\s*(\d+)", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"ROC\s+temperature.*?(\d+)", text, re.I)
    return int(m.group(1)) if m else None


def parse_ctrl_temp(text: str | None) -> int | None:
    """解析 Controller（板载环境）温度，与 ROC 是不同传感器（v2.3.1 起分开）。

    Args:
        text (str | None): storcli 文本输出。

    Returns:
        int | None: 温度（℃）；未匹配或入参为空返回 None。
    """
    if not text:
        return None
    m = re.search(r"Controller\s+Temperature\s*=?\s*(\d+)", text, re.I)
    return int(m.group(1)) if m else None


def parse_cachevault(out: str | None) -> tuple[str, str | None]:
    """解析 CacheVault/BBU 状态，多格式兼容（CVPMxx / CacheVault_Info / 老卡 BBU）。

    Args:
        out (str | None): storcli 文本输出。

    Returns:
        tuple[str, str | None]: (展示文案, 小写状态码)；未检测到返回 ("未检测到", None)。
    """
    if not out:
        return "未检测到", None
    m = re.search(r"(CVPM\w+)\s+(\S+)\s+(\d+C|\d+\s*°C|-+|N/A|n/a|--)", out, re.I)
    if m:
        cvpm, status, temp = m.group(1), m.group(2).strip(), m.group(3).strip()
        temp_disp = temp if temp not in ("-", "--", "N/A", "n/a", "") else "-"
        return f"{cvpm} {status.title()} {temp_disp}".strip(), status.lower()
    m = re.search(r"CacheVault[\s\S]{0,200}?Status\s*=\s*(\S+)", out, re.I)
    if m:
        status = m.group(1).strip()
        return f"CacheVault {status}", status.lower()
    m = re.search(r"CacheVault\s*=\s*(\S+)", out, re.I)
    if m:
        status = m.group(1).strip()
        return f"CacheVault {status}", status.lower()
    m = re.search(r"BBU\s+(\S+)\s+(\d+C|\d+\s*°C|-+|N/A|n/a|--)", out, re.I)
    if m:
        status = m.group(1).strip()
        return f"BBU {status.title()}", status.lower()
    m = re.search(r"BBU[\s\S]{0,200}?Status\s*=\s*(\S+)", out, re.I)
    if m:
        status = m.group(1).strip()
        return f"BBU {status}", status.lower()
    return "未检测到", None


def parse_vds_from_topology(out: str) -> list[dict]:
    """/c0 show 的 Virtual Drives 表 → VD 元信息（JBOD 过滤；分隔线仅跳过）。

    Args:
        out (str): `/c0 show` 文本输出。

    Returns:
        list[dict]: 每项 {dgvd, type, state, access, consist, cache_code, size, name,
            write_policy, read_policy, read_cache, cache_raw}（策略字段留待
            apply_cache_policies 回填）。
    """
    vds: list[dict] = []
    in_topo = False
    for line in out.splitlines():
        s = line.strip()
        if "DG/VD" in s.upper() and "TYPE" in s.upper() and "STATE" in s.upper():
            in_topo = True
            continue
        if not in_topo or not s:
            continue
        if re.match(r"^[-=]+$", s):
            continue
        parts = s.split()
        # 数据行首列必为 DG/VD 形如 0/0；其余实质行（"Physical Drives = 3"、图例）结束表格
        if len(parts) < 6 or not re.match(r"^\d+/\d+$", parts[0]):
            in_topo = False
            continue
        dgvd, vtype, state, access, consist, cache_code = parts[:6]
        if vtype.upper() == "JBOD":
            continue  # JBOD 直通盘不是逻辑盘
        rest = parts[6:]
        size, name = "", ""
        for i, tok in enumerate(rest):
            if re.match(r"^\d+(\.\d+)?$", tok):
                unit = rest[i + 1] if len(rest) > i + 1 and re.match(r"^[TGMK]B?$", rest[i + 1]) else ""
                size = tok + ((f" {unit}") if unit else "")
                name = " ".join(rest[i + 2:]) if len(rest) > i + 2 else ""
                break
        vds.append(
            {
                "dgvd": dgvd, "type": vtype, "state": state, "access": access,
                "consist": consist, "cache_code": cache_code,
                "size": size, "name": name,
                "write_policy": "", "read_policy": "", "read_cache": "", "cache_raw": "",
            }
        )
    return vds


def parse_vd_cache_policies(vd_out: str) -> dict[str, str]:
    """/c0/vall show 按 DG/VD 块解析 Default Cache Policy。

    Args:
        vd_out (str): `/c0/vall show` 文本输出。

    Returns:
        dict[str, str]: {DG/VD（或回退 VD 编号）: 策略文本}；块内无策略记空串。
    """
    res: dict[str, str] = {}
    if not vd_out:
        return res
    anchors = [(m.start(), m.group(1)) for m in re.finditer(r"DG/VD:\s*(\d+/\d+)", vd_out)]
    if not anchors:
        anchors = [(m.start(), m.group(1)) for m in re.finditer(r"Virtual Drive:\s*(\d+)", vd_out)]
    for i, (pos, key) in enumerate(anchors):
        block = vd_out[pos : anchors[i + 1][0] if i + 1 < len(anchors) else len(vd_out)]
        cp = re.search(r"Default Cache Policy\s*:\s*(.+)", block)
        res[key] = cp.group(1).strip() if cp else ""
    return res


def _pd_health_from_storcli(out: str) -> dict:
    """/cN/eN/sN show all 里的阵列卡侧健康字段（不额外增加命令）。

    Args:
        out (str): 单盘 show all 文本。

    Returns:
        dict: {media_err, other_err, bbm_err, pred_fail, shield, temp, smart_alert,
            endurance_used}，仅包含匹配到的字段。
    """
    d: dict = {}
    for key, pat in (
        ("media_err", r"Media Error Count\s*=\s*(\d+)"),
        ("other_err", r"Other Error Count\s*=\s*(\d+)"),
        ("bbm_err", r"BBM Error Count\s*=\s*(\d+)"),
        ("pred_fail", r"Predictive Failure Count\s*=\s*(\d+)"),
        ("shield", r"Shield Counter\s*=\s*(\d+)"),
    ):
        m = re.search(pat, out)
        if m:
            try:
                d[key] = int(m.group(1))
            except Exception:
                pass
    m = re.search(r"Drive Temperature\s*=\s*(-?\d+)\s*C", out)
    if m:
        d["temp"] = int(m.group(1))
    m = re.search(r"S\.M\.A\.R\.T alert flagged by drive\s*=\s*(Yes|No)", out, re.I)
    if m:
        d["smart_alert"] = m.group(1).strip().lower() == "yes"
    m = re.search(r"Percentage Endurance Utilized\s*=\s*([\d.]+)", out)
    if m:
        try:
            d["endurance_used"] = int(float(m.group(1)))
        except Exception:
            pass
    return d


def parse_pd_show_all(out: str) -> dict[tuple[str, str], dict]:
    """/c0/eall/sall show all → {(eid, slot): {sn, model, temp, wwn, fw, raw_size, state, dg, health}}。

    键值对格式天然不受 PD LIST 列偏移影响（旧版 v2.3.0 修复）；
    拿不到的字段一律不塞进结果（不猜、不造假数据）。

    Args:
        out (str): show all 文本输出（空串/None 返回空表）。

    Returns:
        dict[tuple[str, str], dict]: 以 (enclosure, slot) 为键的盘记录。
    """
    res: dict[tuple[str, str], dict] = {}
    if not out:
        return res
    chunks = re.split(r"^Drive /c(\d+)/e(\d+)/s(\d+)\s*:", out, flags=re.M)
    for i in range(1, len(chunks) - 3, 4):
        eid, slot, body = chunks[i + 1], chunks[i + 2], chunks[i + 3]
        rec = res.setdefault((eid, slot), {})
        for key, pat in (
            ("sn", r"^SN\s*=\s*(\S+)"),
            ("model", r"^Model Number\s*=\s*(.+?)\s*$"),
            ("wwn", r"^WWN\s*=\s*(\S+)"),
            ("fw", r"^Firmware Revision\s*=\s*(\S+)"),
            ("raw_size", r"^Raw size\s*=\s*([\d.]+\s*\w+)"),
        ):
            m = re.search(pat, body, re.M)
            if m and m.group(1).strip() not in ("", "N/A", "NA", "-"):
                rec[key] = m.group(1).strip()
        health = _pd_health_from_storcli(body)
        if health:
            rec.setdefault("health", {}).update(health)
            if health.get("temp") is not None:
                rec["temp"] = health["temp"]
        m = re.search(r"^\s*(\d+:\d+)\s+\d+\s+(\S+)\s+(\S+)\s", body, re.M)
        if m:
            rec["state"] = m.group(2)
            rec["dg"] = m.group(3)
    return res


def apply_cache_policies(vds: list[dict], cp_map: dict[str, str]) -> None:
    """把 /c0/vall show 的缓存策略合并进 VD 列表（原位修改）。

    Args:
        vds (list[dict]): parse_vds_from_topology 输出的 VD 列表（原位回填
            cache_raw/write_policy/read_policy/read_cache）。
        cp_map (dict[str, str]): parse_vd_cache_policies 输出；无策略时按
            cache 编码位推写策略（W=WriteBack、T=WriteThrough）。
    """
    for v in vds:
        raw = cp_map.get(v["dgvd"], "")
        up = raw.upper()
        if up:
            v["cache_raw"] = raw
            v["write_policy"] = "WriteBack" if "WRITEBACK" in up else ("WriteThrough" if "WRITETHROUGH" in up else "")
            v["read_policy"] = "NoReadAhead" if "NOREADAHEAD" in up else ("ReadAhead" if "READAHEAD" in up else "")
            v["read_cache"] = "Cached" if "CACHED" in up else ("Direct" if "DIRECT" in up else "")
        else:
            code = (v.get("cache_code") or "").upper()
            v["cache_raw"] = code
            if len(code) > 1 and code[1] == "W":
                v["write_policy"] = "WriteBack"
            elif len(code) > 1 and code[1] == "T":
                v["write_policy"] = "WriteThrough"


def collect(run) -> dict:
    """采集阵列卡全量信息（阻塞调用，调用方应用线程池包装；结果带 15s TTL）。

    Args:
        run (Callable): storcli 文本输出执行器，签名 run(args: list[str], timeout: float) -> str
            （注入便于测试桩替身）。

    Returns:
        dict: {ok, mode(mega|hba|none|mega_error), model, note, controller{...},
            drives[], virtual_drives[], hotspares[]}；storcli 缺失/失败统一降级
            （ok=False、mode="none"、错误落 note，不抛出）。
    """
    with _lock:
        if time.monotonic() - _cache["ts"] < _TTL and _cache["data"] is not None:
            return _cache["data"]
        try:
            data = _collect_uncached(run)
        except Exception as exc:  # noqa: BLE001 storcli 缺失/失败统一降级
            data = {
                "ok": False, "mode": "none", "model": "未检测到",
                "note": f"storcli 不可用: {exc}",
                "controller": None, "drives": [], "virtual_drives": [], "hotspares": [],
            }
        _cache.update(ts=time.monotonic(), data=data)
        return data


def _collect_uncached(run) -> dict:
    """collect 的无缓存执行体（调用方持 _lock）。

    Args:
        run (Callable): storcli 文本输出执行器（签名同 collect.run）。

    Returns:
        dict: 形状同 collect 返回值；MegaRAID 走完整解析（控制器/物理盘/VD/热备），
            非 MegaRAID（HBA 直通或纯主板）时 ok=False、note 说明原因。
    """
    data: dict = {
        "ok": False, "mode": "none", "model": "未检测到", "note": "",
        "controller": None, "drives": [], "virtual_drives": [], "hotspares": [],
    }
    out = run(["/c0", "show"], 30)
    # ---- MegaRAID（IR 模式）----
    if out and "Product Name" in out:
        grab = lambda pat, default="": (m.group(1).strip() if (m := re.search(pat, out)) else default)  # noqa: E731

        data.update(ok=True, mode="mega")
        data["model"] = grab(r"Product Name\s*=\s*(.+)")
        ctrl = {
            "model": data["model"],
            "serial": grab(r"Serial Number\s*=\s*(\S+)"),
            "fw_version": grab(r"FW Version\s*=\s*(\S+)"),
            "fw_package": grab(r"FW Package Build\s*=\s*(\S+)"),
            "bios_version": grab(r"BIOS Version\s*=\s*(\S+)"),
            "driver": (grab(r"Driver Name\s*=\s*(\S+)") + " " + grab(r"Driver Version\s*=\s*(\S+)")).strip(),
            "pci": grab(r"PCI Address\s*=\s*(\S+)"),
            "jbod_count": int(grab(r"JBOD Drives\s*=\s*(\d+)", "0") or 0),
        }
        cv_text, cv_status = parse_cachevault(out)
        ctrl["cachevault"] = cv_text
        ctrl["cachevault_status"] = cv_status
        temp_out = None
        roc = parse_roc_temp(out)
        if roc is None:
            temp_out = run(["/c0", "show", "temperature"], 10)
            roc = parse_roc_temp(temp_out)
        ctl = parse_ctrl_temp(out)
        if ctl is None:
            ctl = parse_ctrl_temp(temp_out if temp_out is not None else run(["/c0", "show", "temperature"], 10))
        ctrl["roc_temp_c"] = roc
        ctrl["controller_temp_c"] = ctl
        data["controller"] = ctrl

        # 物理盘：一条 /c0/eall/sall show all 拿全部（型号/序列号/温度键值对，无列偏移）
        pd_map = parse_pd_show_all(run(["/c0/eall/sall", "show", "all"], 30))
        drives: list[dict] = []
        seen: set[str] = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 12 or not re.match(r"^\d+:\d+$", parts[0]) or parts[0] in seen:
                continue
            seen.add(parts[0])
            eid, slot = parts[0].split(":")
            pd = pd_map.get((eid, slot)) or {}
            tbl_model = parts[-3] if len(parts) >= 3 and parts[-1] in ("-", "SSD", "HDD", "SAS", "SATA") else ""
            model = tbl_model or (pd.get("model") if pd.get("model") not in (None, "-") else "") or ""
            state = parts[2].upper()
            drives.append(
                {
                    "slot": parts[0],
                    "state": parts[2],
                    "dg": parts[3],
                    "size": size_to_decimal(parts[4] + " " + parts[5]),
                    "intf": parts[6],
                    "media": parts[7],
                    "model": model,
                    "sn": pd.get("sn", ""),
                    "brand": disk_brand(resolve_brand_model(tbl_model, pd.get("model", ""))),
                    "temp_c": pd.get("temp"),
                    "media_err": (pd.get("health") or {}).get("media_err"),
                    "failed": "FAILED" in state or "RBAD" in state or "UBAD" in state,
                    "copyback_active": "COPYBACK" in state,
                    "hotspare": "global" if "GHS" in state else ("dedicated" if "DHS" in state else None),
                }
            )
        data["drives"] = drives
        data["hotspares"] = [d for d in drives if d["hotspare"]]

        cb_out = run(["/c0", "show", "copyback"], 10)
        m = re.search(r"Auto\s+CopyBack\s*:\s*(\w+)", cb_out or "")
        data["controller"]["auto_copyback"] = m.group(1).strip().lower() if m else "unknown"

        # 逻辑盘 + 缓存策略
        vds = parse_vds_from_topology(out)
        if vds:
            apply_cache_policies(vds, parse_vd_cache_policies(run(["/c0", "/vall", "show"], 30)))
        data["virtual_drives"] = vds
        return data

    # ---- 非 MegaRAID：HBA 直通 / 纯主板 ----
    data["note"] = (
        "storcli 可用但 /c0 未返回 MegaRAID 控制器（可能为 HBA 直通模式或纯主板 SATA）。"
        if out
        else "storcli 不可用（未安装或无执行权限），阵列卡信息不可用。"
    )
    return data


def detect_controllers(lspci_out: str | None) -> list[dict]:
    """lspci -nn 检测存储控制器，区分 MegaRAID(IR) 与 HBA(IT) 直通（旧版移植）。

    只按设备类型识别（RAID/SAS/SCSI/HBA），不限制厂商白名单——LSI/Broadcom/
    Areca/HighPoint/Adaptec 任意品牌阵列卡/HBA 都能纳入。

    Args:
        lspci_out (str | None): `lspci -nn` 文本输出（None 按空处理）。

    Returns:
        list[dict]: 每项 {model, is_megaraid, is_hba}；无匹配返回 []。
    """
    controllers = []
    for line in (lspci_out or "").splitlines():
        if not re.search(r"(RAID|SAS|SCSI|HBA)", line, re.I):
            continue
        m = re.search(r":\s*(.+)$", line)
        model = m.group(1).strip() if m else line.strip()
        is_megaraid = bool(re.search("MegaRAID", line, re.I))
        is_hba = bool(re.search(r"SAS|HBA", line, re.I)) and not is_megaraid
        controllers.append({"model": model, "is_megaraid": is_megaraid, "is_hba": is_hba})
    return controllers


HBA_NOTE = (
    "HBA 直通卡（IT 模式）：磁盘由内核直接管理，不经阵列卡固件，storcli 无硬 RAID 可报。"
    "每块物理盘的温度与 SMART 见「硬盘」页，阵列由软 RAID（mdstat）或卷管理呈现。"
)
