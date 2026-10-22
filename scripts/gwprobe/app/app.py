#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针入口 shim（与生产包 fpk/app/app.py 同职责）。

1. 飞牛应用中心经 /app/app.py 软链做第三方应用健康检（cmd/main start 时重建软链），
   本文件必须存在于应用根目录，缺失则 start 报 10500（真机实测教训）；
2. 直接执行 `python app.py` ≙ cmd/main start 拉起的 server.py。
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("GWPROBE_SOCK", str(HERE / "gwprobe.sock"))
sys.path.insert(0, str(HERE))

from server import main as server_main  # noqa: E402

if __name__ == "__main__":
    server_main()
