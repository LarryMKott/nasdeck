"""容器 IO 采集 / 1m 桶落库 / 控制校验回归（花活二期 M）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.services.system import container_points, docker, ports
from types import SimpleNamespace
from app.services.system.container_points import ContainerPoint


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_marks():
    docker._prev_io.clear()
    container_points.reset_for_test()
    yield
    docker._prev_io.clear()
    container_points.reset_for_test()


@pytest.fixture
def cgroup_root(tmp_path, monkeypatch):
    root = tmp_path / "cgroup"
    root.mkdir()
    monkeypatch.setattr(docker, "_CGROUP_V2_ROOT", root)
    return root


def _make_v2_io(root, cid: str, rbytes: int, wbytes: int):
    d = root / "system.slice" / f"docker-{cid}.scope"
    d.mkdir(parents=True, exist_ok=True)
    # 双设备行：io.stat 按设备逐行，需跨行求和
    (d / "io.stat").write_text(f"8:0 rbytes={rbytes // 2} wbytes={wbytes // 2} rios=1\n8:16 rbytes={rbytes - rbytes // 2} wbytes={wbytes - wbytes // 2}\n")


def test_cgroup_io_sums_devices_and_v1_absent(cgroup_root):
    _make_v2_io(cgroup_root, "a" * 64, rbytes=2000, wbytes=800)
    assert docker._cgroup_io("a" * 64) == (2000, 800)
    assert docker._cgroup_io("b" * 64) == (None, None)  # 无 v2 目录


def test_container_io_bps_differential(cgroup_root, monkeypatch):
    _make_v2_io(cgroup_root, "c" * 64, rbytes=1000, wbytes=500)
    clock = {"t": 100.0}
    monkeypatch.setattr(docker.time, "monotonic", lambda: clock["t"])
    cid = "c" * 12
    assert docker.container_io_bps(cid, "c" * 64) == (None, None)  # 首采无增量
    clock["t"] = 104.0
    _make_v2_io(cgroup_root, "c" * 64, rbytes=5000, wbytes=2500)
    read_bps, write_bps = docker.container_io_bps(cid, "c" * 64)
    assert read_bps == 1000.0  # 4000B / 4s
    assert write_bps == 500.0
    # 计数回绕 → None（合法真值）
    clock["t"] = 108.0
    _make_v2_io(cgroup_root, "c" * 64, rbytes=10, wbytes=10)
    assert docker.container_io_bps(cid, "c" * 64) == (None, None)


async def test_record_tick_overwrites_and_prunes(db, monkeypatch):
    now = datetime.now(UTC)

    async def _fake_containers():
        return {
            "available": True,
            "reason": None,
            "containers": [
                {"name": "plex", "state": "running", "cpu_percent": 3.2, "mem_bytes": 200 * 1024**2,
                 "read_bps": 2048.0, "write_bps": None},
                {"name": "old", "state": "exited", "cpu_percent": None, "mem_bytes": None,
                 "read_bps": None, "write_bps": None},
            ],
        }

    monkeypatch.setattr(container_points.docker_service, "list_containers", _fake_containers)
    assert await container_points.record_tick(db, now=now) == 1  # 只记 running
    await db.commit()
    assert await container_points.record_tick(db, now=now) == 1  # 同桶覆盖
    rows = (await db.execute(container_points.ContainerPoint.__table__.select())).fetchall()
    assert len(rows) == 1
    r = rows[0]
    assert r.cpu_percent == 3.2 and r.mem_mb == 200.0 and r.read_kbps == 2.0 and r.write_kbps is None

    # 8 天前的桶被翻日清理回收
    old = now - timedelta(days=8)
    db.add(ContainerPoint(ts=old.strftime("%Y-%m-%dT%H:%M:00"), name="plex", cpu_percent=1.0))
    await db.commit()
    monkeypatch.setattr(container_points, "_last_day", None)  # 强制翻日
    await container_points.record_tick(db, now=now)
    await db.commit()
    left = (await db.execute(container_points.ContainerPoint.__table__.select())).fetchall()
    assert all(row.ts >= (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S") for row in left)


async def test_trend_window(db):
    now = datetime.now(UTC)
    for i in range(3):
        db.add(
            ContainerPoint(
                ts=(now - timedelta(minutes=2 - i)).strftime("%Y-%m-%dT%H:%M:00"),
                name="plex",
                cpu_percent=1.0 + i,
            )
        )
    await db.commit()
    r = await container_points.trend(db, "plex", 24)
    assert r["name"] == "plex" and len(r["points"]) == 3
    assert r["points"][0]["cpu_percent"] == 1.0
    empty = await container_points.trend(db, "nope", 24)
    assert empty["points"] == []


async def test_control_validation_rejects(db):
    from app.core.exceptions import InvalidParamsError

    with pytest.raises(InvalidParamsError):
        await docker.container_control("plex", "rm")  # action 白名单外
    with pytest.raises(InvalidParamsError):
        await docker.container_control("bad name;rm -rf", "start")  # 注入形态


def test_is_lan_classification():
    assert ports._is_lan("192.168.31.5") is True
    assert ports._is_lan("10.0.0.1") is True
    assert ports._is_lan("127.0.0.1") is True
    assert ports._is_lan("fe80::1") is True
    assert ports._is_lan("8.8.8.8") is False
    assert ports._is_lan("not-an-ip") is False


def test_network_map_aggregation(monkeypatch):
    import psutil

    from app.services.system import ports

    conns = [
        SimpleNamespace(status=psutil.CONN_LISTEN, raddr=None, laddr=SimpleNamespace(ip="0.0.0.0", port=9800)),
        SimpleNamespace(status=psutil.CONN_ESTABLISHED, raddr=SimpleNamespace(ip="192.168.31.240", port=5522), laddr=None),
        SimpleNamespace(status=psutil.CONN_ESTABLISHED, raddr=SimpleNamespace(ip="192.168.31.240", port=5523), laddr=None),
        SimpleNamespace(status=psutil.CONN_ESTABLISHED, raddr=SimpleNamespace(ip="1.2.3.4", port=443), laddr=None),
    ]
    monkeypatch.setattr(ports.psutil, "net_connections", lambda kind="inet": conns)
    r = ports.network_map()
    assert r["listening"] == 1 and r["established"] == 3
    assert r["lan"] == 2 and r["wan"] == 1
    assert r["remotes"][0] == {"ip": "192.168.31.240", "lan": True, "count": 2}
