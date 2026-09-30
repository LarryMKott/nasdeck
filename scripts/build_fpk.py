#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nasdeck FPK 打包脚本：前端构建 → 依赖离线装配 → 组包 → 校验 → .fpk 产物。

产物：build/fpk/nasdeck-fnpack-<version>.fpk（标准 fnpack 布局，应用中心可装）。
用法（Windows 开发机 / Git Bash）：
    backend/.venv/Scripts/python.exe scripts/build_fpk.py [选项]

选项：
    --skip-frontend    复用 frontend/dist 现有产物（须为 --mode fpk 构建）
    --builder auto|fnpack|manual   打包器：auto=官方 fnpack 优先、失败回退手工
                       （默认 auto）；manual=纯 tarfile（真机验证过的老格式，
                       显式设置可执行位，Windows 下最稳）
    --skip-fnpack-download  不自动下载 fnpack（仅想用手工打包时省流量）

设计要点（为什么这样做，见 fpk/README.md）：
- Python 依赖在打包机交叉安装为 Linux x86_64 cp312 site-packages 随包离线分发，
  装机不联网、不污染系统 Python；解释器来自应用中心 python312 运行时
  （manifest install_dep_apps=python312）。
- 版本号唯一来源 backend/pyproject.toml，注入 fpk/manifest 的 @VERSION@。
- 校验项与 fnpack 1.2.3 官方检查对齐（manifest 字段 / config JSON / 图标尺寸 /
  app、cmd、wizard、app/ui 目录），另加随包内容自检。
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FNP_DIR = ROOT / "fpk"
BUILD_DIR = ROOT / "build" / "fpk"
STAGING = BUILD_DIR / "pkg"
TOOLS_DIR = BUILD_DIR / "tools"

FNPACK_VERSION = "1.2.3"
FNPACK_URL = f"https://static2.fnnas.com/fnpack/fnpack-{FNPACK_VERSION}-windows-amd64"

# 交叉安装目标平台（可重复传给 pip；manylinux2014 兼容面最大，2_28 兜新版本轮子）
TARGET_PLATFORMS = ["manylinux2014_x86_64", "manylinux_2_28_x86_64"]
TARGET_PY = "3.12"
TARGET_ABI = "cp312"

EXEC_FILES = {"app.py", "index.cgi", "storcli64"}  # 打包时显式置 0755 的零散文件
# cmd/ 与 server/bin/ 目录下的文件整体置 0755（见 is_exec）


def log(msg: str) -> None:
    print(f"[build_fpk] {msg}", flush=True)


def die(msg: str) -> None:
    log(f"FATAL: {msg}")
    sys.exit(1)


# ---------------------------------------------------------------- 版本与清单

def read_version() -> str:
    import tomllib

    data = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def read_dependencies() -> list[str]:
    import tomllib

    data = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def render_manifest(version: str) -> str:
    text = (FNP_DIR / "manifest").read_text(encoding="utf-8")
    if "@VERSION@" not in text:
        die("fpk/manifest 缺少 @VERSION@ 占位符")
    return text.replace("@VERSION@", version)


# ---------------------------------------------------------------- 前端构建

def build_frontend(skip: bool) -> Path:
    dist = ROOT / "frontend" / "dist"
    if skip:
        if not (dist / "index.html").exists():
            die("--skip-frontend 但 frontend/dist/index.html 不存在，请先完整构建")
        log("跳过前端构建，复用现有 dist（注意必须是 --mode fpk 的产物）")
        return dist
    log("构建前端（vite build --mode fpk，base= cgi 反代前缀）...")
    proc = subprocess.run(
        "pnpm build --mode fpk",
        shell=True,
        cwd=ROOT / "frontend",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout or "")
        sys.stderr.write(proc.stderr or "")
        die("前端构建失败")
    if not (dist / "index.html").exists():
        die("前端构建后 dist/index.html 仍不存在")
    return dist


# ---------------------------------------------------------------- 纯 Python PNG

def png_read(path: Path) -> tuple[int, int, bytearray]:
    """解码 8-bit RGBA 非隔行 PNG → (w, h, 像素缓冲 RGBA)。"""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        die(f"{path.name} 不是 PNG")
    pos, idat = 8, bytearray()
    w = h = depth = ctype = interlace = 0
    while pos < len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        typ = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if typ == b"IHDR":
            w, h = int.from_bytes(chunk[0:4], "big"), int.from_bytes(chunk[4:8], "big")
            depth, ctype, interlace = chunk[8], chunk[9], chunk[12]
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
    if (depth, ctype, interlace) != (8, 6, 0):
        die(f"{path.name} 需为 8-bit RGBA 非隔行 PNG（实际 depth={depth} ctype={ctype} interlace={interlace}）")
    raw = zlib.decompress(bytes(idat))
    stride = w * 4
    out, prev = bytearray(), bytearray(stride)
    i = 0
    for _ in range(h):
        f = raw[i]
        i += 1
        line = bytearray(raw[i : i + stride])
        i += stride
        if f == 1:  # Sub
            for x in range(4, stride):
                line[x] = (line[x] + line[x - 4]) & 255
        elif f == 2:  # Up
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:  # Average
            for x in range(stride):
                a = line[x - 4] if x >= 4 else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:  # Paeth
            for x in range(stride):
                a = line[x - 4] if x >= 4 else 0
                b = prev[x]
                c = prev[x - 4] if x >= 4 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        out += line
        prev = line
    return w, h, out


def png_downscale(w: int, h: int, px: bytearray, factor: int) -> tuple[int, int, bytearray]:
    """整倍数 box 降采样（预乘 alpha 再平均，避免边缘暗晕）。"""
    nw, nh = w // factor, h // factor
    out = bytearray(nw * nh * 4)
    di = 0
    for y in range(nh):
        for x in range(nw):
            r = g = b = a = 0
            for dy in range(factor):
                srow = ((y * factor + dy) * w + x * factor) * 4
                for dx in range(factor):
                    o = srow + dx * 4
                    aa = px[o + 3]
                    r += px[o] * aa
                    g += px[o + 1] * aa
                    b += px[o + 2] * aa
                    a += aa
            n = factor * factor
            if a:
                out[di], out[di + 1], out[di + 2], out[di + 3] = r // a, g // a, b // a, a // n
            di += 4
    return nw, nh, out


def png_write(path: Path, w: int, h: int, px: bytearray) -> None:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return len(data).to_bytes(4, "big") + typ + data + zlib.crc32(typ + data).to_bytes(4, "big")

    stride = w * 4
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += px[y * stride : (y + 1) * stride]
    ihdr = w.to_bytes(4, "big") + h.to_bytes(4, "big") + bytes([8, 6, 0, 0, 0])
    blob = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(blob)


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:33]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    return struct.unpack(">II", head[16:24])


def render_logo(size: int) -> tuple[int, int, bytearray]:
    """几何重绘 frontend/src/assets/images/logo.svg（32 viewBox：圆角方块 #409eff + 白 V）。

    图标源文件（仓库根 ICON*.PNG）被移出仓库后的兜底方案：SVG 只含基础形状，
    按几何定义 + 4x 超采样精确重绘，效果与原矢量一致。
    """
    ss = 4
    n = size * ss
    u = n / 32.0
    cx = cy = n / 2
    half = n / 2
    rad = 7.0 * u
    w2 = (3.2 * u) / 2
    segs = (((9 * u, 10 * u), (16 * u, 22 * u)), ((16 * u, 22 * u), (23 * u, 10 * u)))
    px = bytearray(n * n * 4)
    i = 0
    for y in range(n):
        py = y + 0.5
        for x in range(n):
            pxc = x + 0.5
            qx = abs(pxc - cx) - (half - rad)
            qy = abs(py - cy) - (half - rad)
            ox, oy = (qx if qx > 0 else 0.0), (qy if qy > 0 else 0.0)
            if (ox * ox + oy * oy) ** 0.5 + min(max(qx, qy), 0.0) - rad < 0:
                ds = 1e18
                for (ax, ay), (bx, by) in segs:
                    vx, vy = bx - ax, by - ay
                    t = ((pxc - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)
                    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                    dx, dy = pxc - (ax + t * vx), py - (ay + t * vy)
                    d2 = dx * dx + dy * dy
                    if d2 < ds:
                        ds = d2
                if ds <= w2 * w2:
                    px[i:i + 4] = b"\xff\xff\xff\xff"
                else:
                    px[i], px[i + 1], px[i + 2], px[i + 3] = 64, 158, 255, 255
            i += 4
    return png_downscale(n, n, px, ss)


def gen_icons(staging: Path) -> None:
    """包根 64/256 图标 + 入口 images/icon_{64,256}.png。优先仓库 ICON_256.PNG，缺失时几何重绘。"""
    src = ROOT / "ICON_256.PNG"
    have_src = src.is_file()
    if have_src:
        w, h, px256 = png_read(src)
        if (w, h) != (256, 256):
            die(f"ICON_256.PNG 尺寸 {(w, h)} 非 256x256")
        log("图标源：仓库 ICON_256.PNG")
    else:
        w, h, px256 = render_logo(256)
        log("图标源：仓库根 ICON_256.PNG 缺失，已按 logo.svg 几何重绘")
    w64, h64, px64 = png_downscale(w, h, px256, 4)
    png_write(staging / "ICON.PNG", w64, h64, px64)
    images = staging / "app" / "ui" / "images"
    images.mkdir(parents=True, exist_ok=True)
    # 官方命名（下划线）：ui/config 的 icon 字段 images/icon_{0}.png 替换后即此名
    png_write(images / "icon_64.png", w64, h64, px64)
    if have_src:
        shutil.copyfile(src, staging / "ICON_256.PNG")
        shutil.copyfile(src, images / "icon_256.png")
    else:
        png_write(staging / "ICON_256.PNG", w, h, px256)
        png_write(images / "icon_256.png", w, h, px256)
    log("图标已生成：ICON.PNG 64px / ICON_256.PNG 256px / ui/images/icon_{64,256}.png")


# ---------------------------------------------------------------- 组装 staging

def copy_backend(staging: Path) -> None:
    server = staging / "app" / "server"
    server.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        ROOT / "backend" / "app",
        server / "app",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copyfile(ROOT / "backend" / "main.py", server / "main.py")
    (server / "bin").mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "backend" / "bin" / "storcli64", server / "bin" / "storcli64")
    log("后端代码与 storcli64 已复制")


def install_site_packages(staging: Path, python: Path) -> None:
    """交叉安装 Linux x86_64 cp312 依赖到随包 site-packages（离线分发，装机不联网）。"""
    site = staging / "app" / "server" / "site-packages"
    deps = read_dependencies()
    log(f"交叉安装 {len(deps)} 个运行依赖 → site-packages（{TARGET_PLATFORMS[0]} …）")
    cmd = [str(python), "-m", "pip", "install", "--target", str(site), "--no-compile",
           "--no-cache-dir", "--disable-pip-version-check"]
    for plat in TARGET_PLATFORMS:
        cmd += ["--platform", plat]
    cmd += ["--python-version", TARGET_PY, "--implementation", "cp", "--abi", TARGET_ABI, "--only-binary=:all:", *deps]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout or "")
        sys.stderr.write(proc.stderr or "")
        die("依赖交叉安装失败（检查 pip 版本 >= 21 或网络）")
    for name in ("fastapi", "uvicorn", "sqlalchemy", "psutil"):
        if not (site / name).exists():
            die(f"site-packages 缺少 {name}，交叉安装不完整")
    log("site-packages 就绪（离线可用）")


def copy_frontend(dist: Path, staging: Path) -> None:
    target = staging / "app" / "server" / "web" / "dist"
    shutil.copytree(dist, target, ignore=shutil.ignore_patterns("__pycache__"))
    if not (target / "index.html").exists():
        die("前端 dist 缺少 index.html")
    log("前端产物已复制 → app/server/web/dist")


def assemble(staging: Path, version: str) -> None:
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    # 应用内容（安装后与系统层合并到应用根目录）
    (staging / "app" / "ui").mkdir(parents=True)
    shutil.copyfile(FNP_DIR / "app" / "app.py", staging / "app" / "app.py")
    shutil.copyfile(FNP_DIR / "app" / "ui" / "config", staging / "app" / "ui" / "config")
    shutil.copyfile(FNP_DIR / "app" / "ui" / "index.cgi", staging / "app" / "ui" / "index.cgi")
    # 系统层
    shutil.copytree(FNP_DIR / "cmd", staging / "cmd")
    shutil.copytree(FNP_DIR / "config", staging / "config")
    shutil.copytree(FNP_DIR / "wizard", staging / "wizard")
    (staging / "manifest").write_text(render_manifest(version), encoding="utf-8")
    gen_icons(staging)
    log(f"staging 组装完成：{staging}")


# ---------------------------------------------------------------- 校验（对齐 fnpack 1.2.3）

def validate(staging: Path) -> None:
    errors: list[str] = []

    def need(cond: bool, msg: str) -> None:
        if not cond:
            errors.append(msg)

    # manifest 必要字段
    text = (staging / "manifest").read_text(encoding="utf-8")
    for field in ("appname", "version", "display_name", "desc", "source", "platform", "desktop_uidir"):
        need(f"{field}" in text and f"@VERSION@" not in text, f"manifest 字段缺失或未渲染：{field}")
    appname = next(
        (ln.split("=", 1)[1].strip() for ln in text.splitlines() if ln.strip().startswith("appname")), ""
    )
    need(appname == "com.dashboard.nasdeck", f"appname 异常：{appname}")

    # config JSON 合法性
    for name in ("privilege", "resource"):
        try:
            json.loads((staging / "config" / name).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"config/{name} 不是合法 JSON：{exc}")

    # 图标（官方：包根 64x64 + 256x256，≤1024KB）
    need(png_size(staging / "ICON.PNG") == (64, 64), "ICON.PNG 必须为 64x64")
    need(png_size(staging / "ICON_256.PNG") == (256, 256), "ICON_256.PNG 必须为 256x256")
    for icon in ("ICON.PNG", "ICON_256.PNG"):
        need((staging / icon).stat().st_size <= 1024 * 1024, f"{icon} 超过 1024KB")

    # 目录要求（fnpack：app/、cmd/、wizard/、app/{desktop_uidir}/）+ 9 个生命周期脚本齐全
    for d in ("app", "cmd", "wizard", "app/ui"):
        need((staging / d).is_dir(), f"缺少目录 {d}/")
    for script in (
        "main",
        "install_init", "install_callback",
        "upgrade_init", "upgrade_callback",
        "uninstall_init", "uninstall_callback",
        "config_init", "config_callback",
    ):
        need((staging / "cmd" / script).is_file(), f"缺少 cmd/{script}")

    # 桌面入口：JSON、入口 ID 前缀 = appname、与 desktop_applaunchname 一致、图标两尺寸齐
    try:
        entry = json.loads((staging / "app" / "ui" / "config").read_text(encoding="utf-8"))
        ids = list(entry.get(".url", {}).keys())
        need(bool(ids), "app/ui/config 缺少 .url 入口")
        launch = next((ln.split("=")[1].strip() for ln in text.splitlines() if ln.startswith("desktop_applaunchname")), "")
        need(launch in ids, f"desktop_applaunchname={launch} 未在 ui/config 入口中定义")
        for i in ids:
            need(i.startswith(appname), f"入口 ID {i} 未用 appname 作前缀")
        for size in ("64", "256"):
            need((staging / "app" / "ui" / "images" / f"icon_{size}.png").is_file(), f"缺少入口图标 icon_{size}.png")
        need((staging / "app" / "ui" / "index.cgi").is_file(), "缺少 cgi 反代入口 index.cgi")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"app/ui/config 解析失败：{exc}")

    # 向导（cgi 形态发布版需要安装/卸载说明页 + 运行配置页）
    for f in ("install", "uninstall", "config"):
        need((staging / "wizard" / f).is_file(), f"缺少 wizard/{f}")

    # 随包内容自检
    need((staging / "app" / "app.py").is_file(), "缺少 app/app.py（飞牛健康检软链目标）")
    need((staging / "app" / "server" / "main.py").is_file(), "缺少 app/server/main.py")
    need((staging / "app" / "server" / "app" / "core" / "config.py").is_file(), "缺少后端 app 包")
    need((staging / "app" / "server" / "site-packages" / "fastapi").is_dir(), "site-packages 缺 fastapi")
    need((staging / "app" / "server" / "web" / "dist" / "index.html").is_file(), "缺少前端 dist/index.html")
    bin_storcli = staging / "app" / "server" / "bin" / "storcli64"
    need(bin_storcli.is_file() and bin_storcli.read_bytes()[:4] == b"\x7fELF", "storcli64 缺失或非 Linux ELF")

    if errors:
        for e in errors:
            log(f"校验失败：{e}")
        die(f"共 {len(errors)} 项校验未通过")
    log("校验通过（对齐 fnpack 1.2.3 检查项 + 随包内容自检）")


# ---------------------------------------------------------------- 打包器

def is_exec(rel: str, is_dir: bool) -> bool:
    if is_dir:
        return True
    parts = Path(rel).parts
    if parts[0] == "cmd":  # 生命周期脚本全部可执行
        return True
    if len(parts) >= 2 and parts[0] == "server" and parts[1] == "bin":  # 随包 ELF 工具
        return True
    return Path(rel).name in EXEC_FILES


EPOCH = 0  # 固定时间戳：产物字节可复现


def _tar_gz(path: Path, writer) -> None:
    """gzip 头 mtime=0 + tar 内 mtime=0 → 完全可复现的归档。"""
    import gzip

    with open(path, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tf:
                writer(tf)


def manual_build(staging: Path, out: Path) -> None:
    """老格式（真机验证）：fpk = tar.gz{ app.tgz, cmd/, config/, ICON*, manifest, wizard/ }。

    app.tgz 为 app/ 内容。可执行位显式设置（Windows 构建机拿不到 x 位，
    这是与官方 fnpack 输出的关键差异，也是提供本打包器的根本原因）。
    """

    def add(tf: tarfile.TarFile, base: Path, arcname: str) -> None:
        p = base / arcname
        is_dir = p.is_dir()
        info = tarfile.TarInfo(arcname + ("/" if is_dir else ""))
        info.mode = 0o755 if is_exec(arcname, is_dir) else 0o644
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        info.mtime = EPOCH
        if is_dir:
            info.type = tarfile.DIRTYPE
            tf.addfile(info)
            for child in sorted(p.iterdir()):
                add(tf, base, f"{arcname}/{child.name}")
        else:
            info.size = p.stat().st_size
            with p.open("rb") as fh:
                tf.addfile(info, fh)

    out.parent.mkdir(parents=True, exist_ok=True)
    app_tgz = BUILD_DIR / "app.tgz"

    def write_app_tgz(tf: tarfile.TarFile) -> None:
        for child in sorted((staging / "app").iterdir()):
            add(tf, staging / "app", child.name)

    _tar_gz(app_tgz, write_app_tgz)

    def write_fpk(tf: tarfile.TarFile) -> None:
        add(tf, staging, "cmd")
        add(tf, staging, "config")
        add(tf, staging, "wizard")
        for name in ("ICON.PNG", "ICON_256.PNG", "manifest"):
            add(tf, staging, name)
        info = tarfile.TarInfo("app.tgz")
        info.mode, info.uid, info.gid, info.uname, info.gname, info.mtime = 0o644, 0, 0, "root", "root", EPOCH
        info.size = app_tgz.stat().st_size
        with app_tgz.open("rb") as fh:
            tf.addfile(info, fh)

    _tar_gz(out, write_fpk)
    log(f"手工打包完成 → {out.name}（{out.stat().st_size // 1024} KB）")


def ensure_fnpack() -> Path | None:
    import socket

    socket.setdefaulttimeout(60)
    exe = TOOLS_DIR / "fnpack.exe"
    if exe.is_file():
        return exe
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        log(f"下载 fnpack {FNPACK_VERSION}（windows-amd64）...")
        urllib.request.urlretrieve(FNPACK_URL, exe)  # noqa: S310
        return exe if exe.is_file() and exe.stat().st_size > 1024 else None
    except Exception as exc:  # noqa: BLE001
        log(f"fnpack 下载失败（{exc}），回退手工打包")
        return None


def fnpack_build(exe: Path, staging: Path) -> Path | None:
    proc = subprocess.run(
        [str(exe), "build", "--directory", str(staging)],
        cwd=BUILD_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = f"{proc.stdout or ''}{proc.stderr or ''}"
    log(output.strip()[-800:])
    # fnpack 失败时退出码可能仍为 0，只在 stdout 打印 Packing failed（1.2.3 实测），
    # 不能只信退出码；配合 main() 里先清理旧 *.fpk，杜绝 glob 捞到上次的产物
    if proc.returncode != 0 or "Packing failed" in output:
        return None
    produced = sorted(BUILD_DIR.glob("*.fpk"))
    return produced[-1] if produced else None


def fpk_modes_ok(path: Path) -> bool:
    """检查 fpk 内 cmd/main 是否保留可执行位（Windows 上 fnpack 可能丢 x 位）。"""
    try:
        with tarfile.open(path, "r:gz") as tf:
            for m in tf.getmembers():
                if m.name.rstrip("/.") in ("cmd/main", "app.tgz/cmd/main", "cmd/install_callback"):
                    return bool(m.mode & 0o111)
    except Exception:  # noqa: BLE001
        return False
    return True


def fpk_summary(path: Path) -> None:
    with tarfile.open(path, "r:gz") as tf:
        names = [m.name for m in tf.getmembers()]
    log(f"fpk 顶层条目：{sorted(set(n.split('/')[0] for n in names))}")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="nasdeck FPK 打包")
    parser.add_argument("--skip-frontend", action="store_true", help="复用现有 frontend/dist")
    parser.add_argument("--builder", choices=["auto", "fnpack", "manual"], default="auto")
    parser.add_argument("--skip-fnpack-download", action="store_true")
    parser.add_argument("--python", default=str(ROOT / "backend" / ".venv" / "Scripts" / "python.exe"),
                        help="用于 pip 交叉安装的解释器（只看其 pip，不影响目标平台）")
    args = parser.parse_args()

    t0 = time.time()
    version = read_version()
    log(f"nasdeck v{version} → FPK")

    dist = build_frontend(args.skip_frontend)
    assemble(STAGING, version)
    copy_backend(STAGING)
    install_site_packages(STAGING, Path(args.python))
    copy_frontend(dist, STAGING)
    validate(STAGING)

    out = BUILD_DIR / f"nasdeck-fnpack-{version}.fpk"
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    # 清掉全部旧 .fpk：fnpack 失败退出码可能为 0，防止 glob 误捞上次产物当新包
    for stale in BUILD_DIR.glob("*.fpk"):
        stale.unlink()
        log(f"已清理旧产物 {stale.name}")

    builder = args.builder
    if builder in ("auto", "fnpack") and not args.skip_fnpack_download:
        exe = ensure_fnpack()
        if exe:
            produced = fnpack_build(exe, STAGING)
            if produced and fpk_modes_ok(produced):
                shutil.move(produced, out)
                builder = "fnpack"
            else:
                log("fnpack 产物缺失或可执行位丢失（Windows 已知坑），回退手工打包")
                builder = "manual"
        elif builder == "fnpack":
            die("fnpack 不可用且已指定 --builder fnpack")
    elif builder == "fnpack":
        exe = TOOLS_DIR / "fnpack.exe"
        if not exe.is_file():
            die("--builder fnpack 但 tools 里没有 fnpack.exe（去掉 --skip-fnpack-download 重试）")
        produced = fnpack_build(exe, STAGING)
        if not produced:
            die("fnpack build 失败")
        shutil.move(produced, out)

    if builder in ("auto", "manual"):
        manual_build(STAGING, out)

    fpk_summary(out)
    log(f"完成：{out}（{time.time() - t0:.0f}s）")
    log("安装验证：应用中心 → 手动安装 → 选择该 .fpk（仅限本地测试），或 appcenter-cli install-fpk")


if __name__ == "__main__":
    main()
