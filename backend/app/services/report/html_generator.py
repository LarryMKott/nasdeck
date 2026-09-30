"""HTML 健康报告生成：summary + 磁盘 + 温度 + 告警事件 → 单文件 HTML。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.services.report.desensitizer import desensitize

REPORT_DIR = Path(__file__).resolve().parents[3] / "data" / "reports"


async def generate_health_report(payload: dict, redact: bool) -> dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"health_{ts}.html"
    html = _render(payload, redact)
    (REPORT_DIR / filename).write_text(html, encoding="utf-8")
    return {"filename": filename, "url": f"/api/v1/report/health/{filename}"}


def _render(payload: dict, redact: bool) -> str:
    rows = "".join(
        f"<tr><td>{k}</td><td>{desensitize(str(v), redact)}</td></tr>"
        for k, v in payload.get("kv", {}).items()
    )
    disks = "".join(
        "<tr><td>{device}</td><td>{model}</td><td>{health}</td><td>{temp}</td></tr>".format(
            device=desensitize(str(d.get("device", "")), redact),
            model=desensitize(str(d.get("model", "—")), redact),
            health=d.get("health", "unknown"),
            temp=f"{d['temp_c']} ℃" if d.get("temp_c") is not None else "—",
        )
        for d in payload.get("disks", [])
    )
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>nasdeck 健康报告</title>
<style>body{{font-family:system-ui,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#1d1e21}}
h1{{font-size:20px}} table{{border-collapse:collapse;width:100%;margin:12px 0}}
td,th{{border:1px solid #dfe2e7;padding:6px 10px;font-size:14px}} th{{background:#f6f7f9}}</style></head>
<body><h1>nasdeck 健康报告 · {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}</h1>
<h2>概览</h2><table>{rows}</table>
<h2>磁盘</h2><table><tr><th>设备</th><th>型号</th><th>健康</th><th>温度</th></tr>{disks}</table>
<p style="color:#8b8d95;font-size:12px">nasdeck {settings.app_version} · {'已脱敏' if redact else '未脱敏'}</p>
</body></html>"""
