"""API 集成测试：信封 / 探针 / 实时快照 / CRUD / 错误码（契约 §1/§3）。"""

from __future__ import annotations

from tests.conftest import err, ok


async def test_health(client):
    data = ok(await client.get("/health"))
    assert data == {"status": "healthy"}


async def test_info_has_is_admin(client):
    """§3.3 info 暴露 is_admin（trim 形态透传 X-Trim-Isadmin；测试形态恒 true）。"""
    data = ok(await client.get("/api/v1/system/info"))
    assert data["is_admin"] is True


async def test_realtime_snapshot_shape(client):
    data = ok(await client.get("/api/v1/monitor/realtime"))
    for key in ("ts", "cpu_percent", "cpu_per_core", "mem_total_mb", "mem_available_mb", "net", "uptime_s"):
        assert key in data
    assert isinstance(data["cpu_per_core"], list)
    # 每逻辑核频率（契约 §2.1）：与每核占用等长，取不到的核为 null
    assert isinstance(data["cpu_freq_per_core"], list)
    assert len(data["cpu_freq_per_core"]) == len(data["cpu_per_core"])


async def test_temperatures_empty_on_non_linux(client):
    data = ok(await client.get("/api/v1/monitor/temperatures"))
    assert isinstance(data, list)


async def test_history_query(client):
    data = ok(await client.get("/api/v1/monitor/history?minutes=60&points=50"))
    assert data["minutes"] == 60
    assert isinstance(data["points"], list)


async def test_alert_rule_crud(client):
    created = ok(
        await client.post(
            "/api/v1/alert/rules",
            json={"name": "CPU 高", "metric": "cpu_percent", "comparator": ">", "threshold": 90},
        )
    )
    rule_id = created["id"]
    items = ok(await client.get("/api/v1/alert/rules"))
    assert any(r["id"] == rule_id for r in items)

    updated = ok(await client.put(f"/api/v1/alert/rules/{rule_id}", json={
        "name": "CPU 更高", "metric": "cpu_percent", "comparator": ">", "threshold": 95,
    }))
    assert updated["id"] == rule_id

    deleted = ok(await client.delete(f"/api/v1/alert/rules/{rule_id}"))
    assert deleted["deleted"] is True
    err(await client.delete(f"/api/v1/alert/rules/{rule_id}"), 1001)


async def test_fan_zone_crud(client):
    """§3.4 风区 CRUD：建 → 改名/定速 → 列表在位 → 删除（删除含交还 BIOS 的副作用）。"""
    created = ok(
        await client.post(
            "/api/v1/control/fans",
            json={
                "name": "测试风扇",
                "loop": "chassis",
                "hwmon_name": "nct-test",
                "pwm_channel": 1,
                "mode": "auto",
            },
        )
    )
    zid = created["id"]
    upd = ok(
        await client.put(
            f"/api/v1/control/fans/{zid}",
            json={"name": "改名风扇", "mode": "fixed", "fixed_pwm": 40},
        )
    )
    assert upd["name"] == "改名风扇" and upd["mode"] == "fixed"
    items = ok(await client.get("/api/v1/control/fans"))
    assert any(z["id"] == zid for z in items)
    deleted = ok(await client.delete(f"/api/v1/control/fans/{zid}"))
    assert deleted["deleted"] is True


async def test_alert_rule_invalid_metric(client):
    err(
        await client.post(
            "/api/v1/alert/rules",
            json={"name": "x", "metric": "bogus", "comparator": ">", "threshold": 1},
        ),
        2000,
    )


async def test_curve_validation(client):
    # 温度未递增 → 1002（Pydantic 校验走 2000？契约 §2.17：约束违反 → 1002）
    resp = await client.post(
        "/api/v1/control/curves",
        json={"name": "bad", "points": [[40, 30], [30, 20]]},
    )
    assert resp.status_code in (400, 422)
    body = resp.json()
    assert body["code"] in (1002, 2000)

    created = ok(
        await client.post(
            "/api/v1/control/curves",
            json={"name": "静音优先", "points": [[30, 20], [45, 45], [65, 90]]},
        )
    )
    curve_id = created["id"]
    preview = ok(await client.get(f"/api/v1/control/curves/preview?curve_id={curve_id}&temp=45"))
    assert preview["target_pwm_pct"] == 45.0
    ok(await client.delete(f"/api/v1/control/curves/{curve_id}"))


async def test_settings_upsert(client):
    ok(await client.put("/api/v1/system/settings/theme", json={"value": "dark"}))
    data = ok(await client.get("/api/v1/system/settings"))
    assert data["theme"]["value"] == "dark"


async def test_whitelist_crud(client):
    item = ok(await client.post("/api/v1/system/whitelist", json={"name": "myapp"}))
    ok(await client.delete(f"/api/v1/system/whitelist/{item['id']}"))
    err(await client.delete(f"/api/v1/system/whitelist/{item['id']}"), 1001)


async def test_alias_delete_without_alias(client):
    err(await client.delete("/api/v1/disks/UNKNOWN_SER_IAL/alias".replace("/disks", "/storage/disks")), 1001)


async def test_unknown_device_alias_route(client):
    # 契约：未知资源 → 1001
    err(await client.delete("/api/v1/storage/disks/NOPE123/alias"), 1001)


async def test_api_key_enforced_when_set(client, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "api_key", "secret", raising=False)
    resp = await client.get("/api/v1/monitor/realtime")
    assert resp.status_code == 403
    assert resp.json()["code"] == 1004
    monkeypatch.setattr(config.settings, "api_key", "", raising=False)


async def test_hardware_read_api(client):
    """§3.7：慢采集落库后 /hardware 可读（测试进程未跑 60s 任务时至少结构正确）。"""
    from app.db.session import session_factory
    from app.models.hardware import HardwareItem

    async with session_factory() as db:
        db.add(HardwareItem(kind="cpu", name="Test CPU", props={"available": True, "name": "Test CPU"}))
        await db.commit()
    data = ok(await client.get("/api/v1/hardware"))
    assert "cpu" in data
    one = ok(await client.get("/api/v1/hardware/cpu"))
    assert one["kind"] == "cpu"
    err(await client.get("/api/v1/hardware/nope"), 1001)


async def test_history_stats_and_export(client):
    """§3.1：stats 聚合 + export 文件流（非信封）。"""
    from datetime import UTC, datetime, timedelta

    from app.db.session import session_factory
    from app.models.metrics import MetricPoint

    def iso(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    base = datetime.now(UTC) - timedelta(minutes=5)
    async with session_factory() as db:
        db.add(MetricPoint(ts=iso(base), granularity="raw", cpu=10.0, mem_mb=100.0))
        db.add(MetricPoint(ts=iso(base + timedelta(minutes=1)), granularity="raw", cpu=30.0, mem_mb=200.0))
        await db.commit()
    data = ok(await client.get("/api/v1/monitor/history/stats?minutes=60&dim=cpu"))
    assert data["n"] >= 2 and data["max"] >= 30
    resp = await client.get("/api/v1/monitor/history/export?minutes=60&dim=cpu&fmt=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "ts,value" in resp.text
    resp = await client.get("/api/v1/monitor/history/export?minutes=60&dim=cpu&fmt=bogus")
    assert resp.status_code == 422
