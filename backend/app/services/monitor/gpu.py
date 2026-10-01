"""GPU 实时采集（契约 §2.1 gpu 对象）：策略决策层判定各 vendor 的采集策略。

- AMD：device/gpu_busy_percent + mem_info_vram_{used,total} + hwmon 温度
  ——全部内核导出，纯文本只读（Unraid GPU Statistics 插件同款思路）
- NVIDIA：nvidia-smi --query-gpu 只查需要字段，5s 采样避免高频 fork；
  仅当决策层判定 nvidia-smi 在位才扫描
- Intel：无全局忙闲 sysfs，走 intel_gpu_top -J 长驻子进程（perf PMU，
  1s 一帧 JSON 由后台线程消费），决策层判定工具在位才扫描；核显显存/温度
  无独立传感（共享内存/主板 sensor），对应字段为 None

无卡/读取失败 available=false，调用方按缺数据处理；采集永不抛异常。
"""

from __future__ import annotations

import atexit
import json
import subprocess
import threading
import time

from app.core.exceptions import ExternalToolError
from app.services.hardware.policy import get_policy
from app.utils import sysfs
from app.utils.async_cmd import run_cmd, run_cmd_sync

# vendor key（决策层）→ sysfs vendor id
VENDOR_IDS = {"amd": "0x1002", "nvidia": "0x10de", "intel": "0x8086"}

# 5s 采样缓存：GPU 变化粒度粗，nvidia-smi 是 fork 外部进程（拒绝 1s 高频调用）
_cache: dict = {"ts": 0.0, "data": None}
# 卡枚举 60s 缓存：显卡不会频繁热插拔
_scan_cache: dict = {"ts": 0.0, "cards": None}


def _allowed_vendors() -> dict[str, str]:
    """决策层允许实时采集的 vendor：sysfs vendor id → vendor key。"""
    policy = get_policy()
    return {VENDOR_IDS[key]: key for key, strategy in policy.gpu_vendors.items() if strategy != "unavailable"}


def _scan_cards(base: str = "/sys/class/drm") -> list[dict]:
    """枚举 drm 卡 → [{name, dev, kind}]，只留策略允许实时采集的 vendor。"""
    now = time.monotonic()
    if _scan_cache["cards"] is not None and now - _scan_cache["ts"] < 60.0:
        return _scan_cache["cards"]
    allowed = _allowed_vendors()
    cards = []
    for name in sysfs.list_dirs(base):
        if not name.startswith("card") or not name[4:].isdigit():
            continue
        dev = f"{base}/{name}/device"
        vendor = (sysfs.read_text(f"{dev}/vendor") or "").strip()
        if vendor in allowed:
            cards.append({"name": name, "dev": dev, "kind": allowed[vendor]})
    _scan_cache["cards"] = cards
    _scan_cache["ts"] = now
    return cards


def _amd_card(dev: str) -> dict:
    """AMD 卡实时分量：全 sysfs 直读（busy 为整数百分比，显存单位字节，温度毫摄氏度）。"""
    temp = None
    for hwmon in sysfs.list_dirs(f"{dev}/hwmon"):
        temp = sysfs.read_float(f"{dev}/hwmon/{hwmon}/temp1_input")
        if temp is not None:
            break
    return {
        "percent": sysfs.read_int(f"{dev}/gpu_busy_percent"),
        "vram_used_mb": _bytes_to_mb(sysfs.read_int(f"{dev}/mem_info_vram_used")),
        "vram_total_mb": _bytes_to_mb(sysfs.read_int(f"{dev}/mem_info_vram_total")),
        "temp_c": temp,
    }


def _bytes_to_mb(value: int | None) -> float | None:
    return round(value / 1048576, 1) if value is not None else None


def _parse_nvidia_smi(out: str) -> list[dict]:
    """解析 `--format=csv,noheader,nounits` 输出（每卡一行，缺值 [N/A] → None）。"""
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue

        def num(text: str) -> float | None:
            try:
                return float(text)
            except ValueError:
                return None

        gpus.append(
            {
                "name": parts[0],
                "percent": num(parts[1]),
                "vram_used_mb": num(parts[2]),
                "vram_total_mb": num(parts[3]),
                "temp_c": num(parts[4]),
            }
        )
    return gpus


async def _nvidia_card() -> dict | None:
    """NVIDIA 首卡：只查需要的字段，减少输出文本量与解析开销。"""
    try:
        rc, out, _err = await run_cmd(
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits",
            timeout=10,
        )
    except ExternalToolError:
        return None  # 未装驱动/工具
    gpus = _parse_nvidia_smi(out) if rc == 0 else []
    return gpus[0] if gpus else None


# ---------------------------------------------------------------- Intel


def _engine_busy(obj: dict, prefix: str) -> float | None:
    """取引擎 busy：真机引擎名带序号后缀（Render/3D/0、Video/0），按前缀匹配。"""
    engines = obj.get("engines")
    if not isinstance(engines, dict):
        return None
    busies = [
        e.get("busy")
        for name, e in engines.items()
        if name.startswith(prefix) and isinstance(e, dict) and isinstance(e.get("busy"), (int, float))
    ]
    return round(float(max(busies)), 1) if busies else None


def _frame_num(value) -> float | None:
    return round(float(value), 1) if isinstance(value, (int, float)) else None


def _intel_busy(obj: dict) -> float | None:
    """单帧 intel_gpu_top JSON → 利用率百分比。

    busy 优先取 Render/3D 引擎；结构缺失/变更时退化取各引擎 busy 最大值。
    """
    engines = obj.get("engines")
    if not isinstance(engines, dict) or not engines:
        return None
    busy = _engine_busy(obj, "Render/3D")
    if busy is None:
        busies = [e.get("busy") for e in engines.values() if isinstance(e, dict)]
        busies = [b for b in busies if isinstance(b, (int, float))]
        busy = max(busies) if busies else None
    return round(float(busy), 1) if busy is not None else None


class _IntelFrameParser:
    """流式 JSON 帧提取：真机 intel_gpu_top 各版本输出不一——compact 单行或
    缩进多行（真机 1.2.0701 实测为多行 pretty），raw_decode 增量解析两者通吃。
    """

    def __init__(self) -> None:
        self._buf = ""
        self._dec = json.JSONDecoder()

    def feed(self, text: str) -> dict | None:
        self._buf += text
        self._buf = self._buf.lstrip()
        if not self._buf:
            return None
        try:
            obj, idx = self._dec.raw_decode(self._buf)
        except json.JSONDecodeError:
            # 半帧（'{' 开头）：等后续输入；超限丢弃防失控。
            # 垃圾前缀：跳到下一个 '{'（真机输出为纯 JSON 帧，仅防御性兜底）
            if self._buf.startswith("{"):
                if len(self._buf) > 1_048_576:
                    self._buf = ""
            else:
                brace = self._buf.find("{")
                self._buf = self._buf[brace:] if brace > 0 else ""
            return None
        self._buf = self._buf[idx:]
        return obj


class _IntelTopReader:
    """intel_gpu_top -J 长驻子进程：后台线程逐行消费 JSON 帧，collect() 只取最新值。

    进程生命周期：惰性启动（失败 60s 冷却防频繁 fork）、卡消失/应用退出时终止。
    perf 受限（perf_event_paranoid 过高）时 intel_gpu_top 会持续无输出——
    busy() 按 10s 新鲜度判空，不误报。
    """

    _FRESH_S = 10.0
    _RETRY_S = 60.0

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._latest: tuple[float, float | None, dict] = (0.0, None, {})  # (monotonic, busy, 帧)
        self._name = ""
        self._next_try = 0.0
        self._lock = threading.Lock()

    def ensure(self, card_dev: str, card_name: str) -> None:
        now = time.monotonic()
        if self._proc is not None and self._proc.poll() is None:
            return
        if now < self._next_try:
            return
        self._next_try = now + self._RETRY_S
        if not self._name:
            self._name = self._resolve_name(card_name)
        try:
            self._proc = subprocess.Popen(  # noqa: S603 固定参数无外部输入
                ["intel_gpu_top", "-J", "-s", "1000"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError:
            self._proc = None
            return
        self._thread = threading.Thread(target=self._consume, daemon=True)
        self._thread.start()

    def _consume(self) -> None:
        assert self._proc and self._proc.stdout
        parser = _IntelFrameParser()
        for line in self._proc.stdout:
            obj = parser.feed(line)
            if obj is None:
                continue
            pct = _intel_busy(obj)
            with self._lock:
                self._latest = (time.monotonic(), pct, obj)

    @staticmethod
    def _resolve_name(fallback: str) -> str:
        """lspci 找 Intel VGA/Display 控制器型号（决策层已在位才到这；失败回退 card id）。"""
        try:
            _rc, out, _err = run_cmd_sync("lspci", "-nn", "-d", "8086:", timeout=10)
        except Exception:  # noqa: BLE001 名字拿不到不影响采集
            return fallback
        for line in out.splitlines():
            if "VGA" in line or "Display" in line:
                model = line.split(": ", 1)[-1]
                return model.split(" [8086:")[0].strip() or fallback
        return fallback

    def busy(self) -> float | None:
        with self._lock:
            ts, pct, _obj = self._latest
        return pct if pct is not None and time.monotonic() - ts <= self._FRESH_S else None

    def frame(self) -> dict:
        """最新一帧原始 JSON（超 10s 视为过期返回空），供频率/功耗/引擎占用提取。"""
        with self._lock:
            ts, _pct, obj = self._latest
        return obj if obj and time.monotonic() - ts <= self._FRESH_S else {}

    @property
    def name(self) -> str:
        return self._name

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()


_intel_reader_instance: _IntelTopReader | None = None


def _intel_reader() -> _IntelTopReader:
    global _intel_reader_instance
    if _intel_reader_instance is None:
        _intel_reader_instance = _IntelTopReader()
        atexit.register(_intel_reader_instance.stop)
    return _intel_reader_instance


async def collect() -> dict:
    """GPU 实时快照（5s 采样缓存）：{available, name, percent, vram_used_mb, vram_total_mb, temp_c, source}。

    决策层判定无 /sys/class/drm 或无可用 vendor 策略时直接返回不可用，不扫描不 fork。
    """
    now = time.monotonic()
    if _cache["data"] is not None and now - _cache["ts"] < 5.0:
        return _cache["data"]
    data = {
        "available": False,
        "name": "",
        "percent": None,
        "vram_used_mb": None,
        "vram_total_mb": None,
        "temp_c": None,
        "freq_mhz": None,
        "freq_max_mhz": None,
        "power_w": None,
        "video_busy": None,
        "enhance_busy": None,
        "source": "",
    }
    if get_policy().gpu_scan:
        for card in _scan_cards():
            if card["kind"] == "amd":
                fields = _amd_card(card["dev"])
                if fields["percent"] is not None:
                    data.update(fields, available=True, name=card["name"], source="sysfs")
                    break
            elif card["kind"] == "nvidia":
                fields = await _nvidia_card()
                if fields:
                    data.update(fields, available=True, name=fields.get("name") or card["name"], source="nvidia-smi")
                    break
            elif card["kind"] == "intel":
                reader = _intel_reader()
                reader.ensure(card["dev"], card["name"])
                busy = reader.busy()
                if busy is not None:
                    # 核显温度（i915 hwmon，真机 1.2.0701 有 temp1_input）；无则 None
                    temp = None
                    for hwmon in sysfs.list_dirs(f"{card['dev']}/hwmon"):
                        temp = sysfs.read_float(f"{card['dev']}/hwmon/{hwmon}/temp1_input")
                        if temp is not None:
                            break
                    frame = reader.frame()
                    freq = frame.get("frequency") or {}
                    power = frame.get("power") or {}
                    data.update(
                        percent=busy,
                        temp_c=temp,
                        available=True,
                        name=reader.name or card["name"],
                        source="intel-gpu-top",
                        freq_mhz=_frame_num(freq.get("actual")),
                        freq_max_mhz=_frame_num(freq.get("requested")),
                        # 包功耗优先（GPU 域 RC6 门控时常为 0）
                        power_w=_frame_num(power.get("Package")) or _frame_num(power.get("GPU")),
                        video_busy=_engine_busy(frame, "Video/"),
                        enhance_busy=_engine_busy(frame, "VideoEnhance"),
                    )
                    break
    _cache["data"] = data
    _cache["ts"] = now
    return data
