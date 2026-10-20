#!/usr/bin/env bash
# L3 验收：aarch64 用户态模拟（#18 决策）。
#
# 只做结构校验（L1）不够——ARM 包真正会炸的地方是：依赖 import 失败、DB 初始化
# 走不通、核心接口返回空、前端产物没进包。这里把包解出来，在 arm64 容器里
# 用随包 site-packages 直接跑后端，逐个打接口。
#
# 前置：docker + binfmt qemu（CI 用 docker/setup-qemu-action 装；本机可 apt 装 qemu-user-static）。
# 用法：scripts/acceptance_arm.sh [fpk路径] [报告输出路径]
set -euo pipefail

FPK="${1:-}"
REPORT="${2:-build/fpk/acceptance-report.md}"

if [ -z "$FPK" ]; then
    FPK="$(ls build/fpk/nasdeck_arm-fnpack-*.fpk 2>/dev/null | sort | tail -1 || true)"
fi
if [ -z "$FPK" ] || [ ! -f "$FPK" ]; then
    echo "[L3] 找不到 ARM 包：先跑 scripts/build_fpk.py --arch arm" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "[L3] 没有 docker，无法做 aarch64 用户态模拟；请在本机或 CI 安装 docker + qemu-user-static" >&2
    exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
echo "[L3] 解包 $FPK"
tar -xzf "$FPK" -C "$WORK"
tar -xzf "$WORK/app.tgz" -C "$WORK"

# app.tgz 的顶层有两种可能：直接是 app.py + server/（当前打包器），或 app/ 前缀（旧产物）。
# 不猜，按实际落点确认，避免 PYTHONPATH 指到不存在的目录后「import 不到依赖」被误判成架构问题。
if [ -d "$WORK/server" ]; then
    INNER=""
else
    INNER="/app"
fi
CONTAINER_APP="/w${INNER}"
echo "[L3] 应用根目录（容器内）：$CONTAINER_APP"

# 探针脚本在容器内执行：import → 起服务 → 打核心接口 → 校验架构画像
cat > "$WORK/probe.py" <<'PY'
import asyncio
import json
import os
import sys

results = []

def check(name, fn):
    try:
        value = fn()
        results.append({"check": name, "ok": True, "detail": str(value)[:200]})
        return value
    except Exception as exc:  # noqa: BLE001
        results.append({"check": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
        return None

# 1) 依赖可 import：随包 site-packages 是 aarch64 轮子，x86 机器上 import 必失败
import fastapi, uvicorn, sqlalchemy, psutil  # noqa: E402,F401
check("import-deps", lambda: f"fastapi {fastapi.__version__}")

# 2) 采集层可加载，且架构画像报告 aarch64
from app.services.hardware.policy import build_arch_profile  # noqa: E402
profile = check("arch-profile", build_arch_profile)
check("arch-is-aarch64", lambda: (_ for _ in ()).throw(AssertionError(f"arch={profile.arch}"))
      if profile.arch != "aarch64" else profile.arch)

# 3) 应用可起 + DB 初始化 + 核心接口有数据（字段非空，不是 200 就算过）
import httpx  # noqa: E402
from main import app  # noqa: E402

os.environ.setdefault("NASDECK_DB_URL", "sqlite+aiosqlite:////tmp/l3.db")

async def probe():
    from app.db.init_db import init_db  # noqa: E402
    await init_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://l3") as client:
        health = await client.get("/health")
        results.append({"check": "GET /health", "ok": health.status_code == 200, "detail": health.text[:200]})
        for path in ("/api/v1/system/info", "/api/v1/system/env", "/api/v1/hardware/cpu",
                     "/api/v1/monitor/summary", "/api/v1/storage/volumes"):
            resp = await client.get(path)
            payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            data = payload.get("data", payload)
            ok = resp.status_code == 200 and data not in ({}, [], None, "")
            results.append({"check": f"GET {path}", "ok": bool(ok), "detail": f"{resp.status_code} {str(data)[:160]}"})

asyncio.run(probe())
print(json.dumps({"arch": profile.arch, "results": results}, ensure_ascii=False))
PY

echo "[L3] 在 arm64 容器里跑后端"
if ! OUT="$(docker run --rm --platform linux/arm64 \
        -v "$WORK:/w" -w "$CONTAINER_APP" \
        -e PYTHONPATH="$CONTAINER_APP/server:$CONTAINER_APP/server/site-packages" \
        -e NASDECK_DB_URL=sqlite+aiosqlite:////tmp/l3.db \
        -e NASDECK_STORCLI_PATH=/nonexistent \
        python:3.12-slim python /w/probe.py)"; then
    echo "[L3] 容器执行失败（可能是 binfmt 未装，或后端在 aarch64 上真的起不来）" >&2
    echo "$OUT" >&2
    exit 3
fi
echo "$OUT"

mkdir -p "$(dirname "$REPORT")"
python_bin="$(command -v python3 || command -v python)"
"$python_bin" - "$OUT" "$FPK" "$REPORT" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

raw, fpk, report = sys.argv[1], sys.argv[2], Path(sys.argv[3])
payload = json.loads(raw.strip().splitlines()[-1])
failed = [r for r in payload["results"] if not r["ok"]]
rows = "\n".join(f"| {r['check']} | {'✅' if r['ok'] else '❌'} | {r['detail']} |" for r in payload["results"])
status = "PASS" if not failed else "FAIL"
report.write_text(
    f"""# nasdeck L3 aarch64 用户态模拟验收

- 时间：{datetime.now(timezone.utc).isoformat(timespec="seconds")}
- 包：`{fpk}`
- 检测到的架构：`{payload['arch']}`
- 结论：**{status}**（{len(payload['results']) - len(failed)}/{len(payload['results'])} 项通过）

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
{rows}

> 本报告是 L3 模拟验收，不等于真机可用。真机补验（L4）才是发版阻塞项，见 issue #18。
""",
    encoding="utf-8",
)
print(f"[L3] 报告已写入 {report}")
sys.exit(0 if not failed else 1)
PY
