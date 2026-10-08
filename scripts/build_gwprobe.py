#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网关存活探针打包：scripts/gwprobe/ → build/gwprobe/gatewayprobe-0.0.1.fpk。

复用 build_fpk 的纯 Python PNG 渲染与手工 tar 打包器（真机验证格式，显式可执行位）。
试验包与生产包完全独立：独立 appname（com.test.gatewayprobe）、独立构建目录，
不触碰 fpk/ 下任何生产打包源。

用法（Windows 开发机 / Git Bash）：
    backend/.venv/Scripts/python.exe scripts/build_gwprobe.py
"""
from __future__ import annotations

import shutil
import sys
import tarfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import build_fpk as bf  # noqa: E402  （import 无副作用，main 有 __main__ 守卫）

SRC = SCRIPTS / "gwprobe"
VERSION = "0.0.2"
OUT_DIR = bf.ROOT / "build" / "gwprobe"
STAGING = OUT_DIR / "pkg"


def log(msg: str) -> None:
    print(f"[build_gwprobe] {msg}", flush=True)


def die(msg: str) -> None:
    log(f"FATAL: {msg}")
    sys.exit(1)


def assemble(staging: Path) -> None:
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "app" / "ui").mkdir(parents=True)
    # 系统层
    shutil.copytree(SRC / "cmd", staging / "cmd")
    shutil.copytree(SRC / "config", staging / "config")
    shutil.copytree(SRC / "wizard", staging / "wizard")
    shutil.copyfile(SRC / "manifest", staging / "manifest")
    # 应用内容
    for name in ("app.py", "server.py", "watch.sh"):
        shutil.copyfile(SRC / "app" / name, staging / "app" / name)
    shutil.copyfile(SRC / "app" / "ui" / "config", staging / "app" / "ui" / "config")
    # 图标：几何重绘 logo.svg（与生产包同源，无外部依赖）
    images = staging / "app" / "ui" / "images"
    images.mkdir(parents=True, exist_ok=True)
    _, _, px256 = bf.render_logo(256)
    _, _, px64 = bf.png_downscale(256, 256, px256, 4)
    bf.png_write(staging / "ICON.PNG", 64, 64, px64)
    bf.png_write(staging / "ICON_256.PNG", 256, 256, px256)
    bf.png_write(images / "icon_64.png", 64, 64, px64)
    bf.png_write(images / "icon_256.png", 256, 256, px256)
    log("staging 组装完成")


def validate(staging: Path) -> None:
    errors: list[str] = []
    text = (staging / "manifest").read_text(encoding="utf-8")
    for field in ("appname", "version", "display_name", "desc", "source", "platform", "desktop_uidir"):
        if field not in text:
            errors.append(f"manifest 缺字段：{field}")
    import json

    try:
        entry = json.loads((staging / "app" / "ui" / "config").read_text(encoding="utf-8"))
        ids = list(entry.get(".url", {}))
        if not ids:
            errors.append("ui/config 无 .url 入口")
        gw = entry[".url"][ids[0]]
        for key in ("gatewayPrefix", "gatewaySocket"):
            if key not in gw:
                errors.append(f"网关入口缺 {key}（不是网关形态声明）")
        if gw.get("gatewayPrefix") != "/app/com.test.gatewayprobe":
            errors.append("gatewayPrefix 与 appname 不一致")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ui/config 解析失败：{exc}")
    for d in ("app", "cmd", "wizard", "app/ui"):
        if not (staging / d).is_dir():
            errors.append(f"缺目录 {d}/")
    for script in ("main", "install_init", "install_callback", "upgrade_init", "upgrade_callback",
                   "uninstall_init", "uninstall_callback", "config_init", "config_callback"):
        if not (staging / "cmd" / script).is_file():
            errors.append(f"缺 cmd/{script}")
    if errors:
        for e in errors:
            log(f"校验失败：{e}")
        die(f"共 {len(errors)} 项校验未通过")
    log("校验通过")


def verify_fpk(path: Path) -> None:
    with tarfile.open(path, "r:gz") as tf:
        members = tf.getmembers()
        names = [m.name for m in members]
    top = sorted(set(n.split("/")[0] for n in names))
    log(f"fpk 顶层条目：{top}")
    if "app.tgz" not in top:
        die("fpk 缺 app.tgz")
    for must in ("cmd/main", "cmd/install_callback"):
        m = next((m for m in members if m.name == must), None)
        if m is None:
            die(f"fpk 缺 {must}")
        if not m.mode & 0o111:
            die(f"{must} 可执行位丢失（mode={oct(m.mode)}）")
    if "manifest" not in names:
        die("fpk 缺 manifest")
    log("fpk 结构与可执行位验证通过")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assemble(STAGING)
    validate(STAGING)
    # manual_build 把中间 app.tgz 写进 bf.BUILD_DIR，指向探针自己的构建目录避免混入生产组包区
    bf.BUILD_DIR = OUT_DIR
    out = OUT_DIR / f"gatewayprobe-{VERSION}.fpk"
    bf.manual_build(STAGING, out)
    verify_fpk(out)
    log(f"完成：{out}")


if __name__ == "__main__":
    main()
