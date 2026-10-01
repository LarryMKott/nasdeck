"""intel_gpu_top 帧字段提取：引擎前缀匹配 / 频率 / 功耗 / 读取器新鲜度（monitor/gpu.py）。"""

from __future__ import annotations

import time

from app.services.monitor import gpu

# 真机 1.2.0701 帧形（引擎名带序号后缀）
_FRAME = {
    "frequency": {"requested": 1150.0, "actual": 850.0, "unit": "MHz"},
    "power": {"GPU": 0.0, "Package": 6.785635, "unit": "W"},
    "engines": {
        "Render/3D/0": {"busy": 4.2},
        "Blitter/0": {"busy": 0.0},
        "Video/0": {"busy": 12.5},
        "VideoEnhance/0": {"busy": 3.0},
    },
}


def test_engine_busy_matches_numbered_names():
    assert gpu._engine_busy(_FRAME, "Render/3D") == 4.2
    assert gpu._engine_busy(_FRAME, "Video/") == 12.5  # 不吞 VideoEnhance
    assert gpu._engine_busy(_FRAME, "VideoEnhance") == 3.0
    assert gpu._engine_busy(_FRAME, "Missing") is None


def test_intel_busy_prefers_render():
    assert gpu._intel_busy(_FRAME) == 4.2


def test_intel_busy_falls_back_to_max():
    frame = {"engines": {"Video/0": {"busy": 7.0}, "Blitter/0": {"busy": 2.0}}}
    assert gpu._intel_busy(frame) == 7.0


def test_reader_frame_and_busy_freshness():
    reader = gpu._IntelTopReader()
    reader._latest = (time.monotonic(), 4.2, _FRAME)
    assert reader.busy() == 4.2
    frame = reader.frame()
    assert gpu._frame_num(frame["frequency"]["actual"]) == 850.0
    assert gpu._frame_num(frame["power"]["Package"]) == 6.8
    # 过期帧：busy/frame 均判空
    reader._latest = (time.monotonic() - 60, 4.2, _FRAME)
    assert reader.busy() is None
    assert reader.frame() == {}
