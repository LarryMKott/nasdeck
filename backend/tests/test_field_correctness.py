"""字段级正确性回归：网络接口过滤 / GPU drm 枚举 / SMART 健康判定 / 盘健康缓存。"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.services.hardware.gpu import _CARD_RE
from app.services.monitor import system_resources, temperature
from app.services.storage.smart import _health_of


def test_real_net_names_filters_synthetic_and_bridged(monkeypatch):
    # veth/docker/网桥内部口/被桥接物理口剔除；br- 前缀的真实网桥本身保留（求和靠它）
    # _refresh_bridge_members 会用真实 /sys/class/net 扫描冲掉补丁（CI runner 是新开
    # VM，5s TTL 是否命中纯看时序）——直接停用刷新，测试与运行环境/时序解耦
    monkeypatch.setattr(system_resources, "_refresh_bridge_members", lambda: None)
    monkeypatch.setitem(system_resources._bridge_members, "set", frozenset({"eth0"}))
    names = ["lo", "eth0", "br0", "vethabc123", "docker0", "br-1a2b3c", "virbr0", "eth0-ovs", "ovs-system"]
    assert system_resources._real_net_names(names) == ["br0"]


def test_real_net_names_keeps_normal_ifaces_when_no_bridge(monkeypatch):
    monkeypatch.setattr(system_resources, "_refresh_bridge_members", lambda: None)
    monkeypatch.setitem(system_resources._bridge_members, "set", frozenset())
    assert system_resources._real_net_names(["eth0", "enp3s0", "lo"]) == ["eth0", "enp3s0"]


def test_gpu_card_regex_excludes_connectors():
    assert _CARD_RE.match("card0")
    assert _CARD_RE.match("card12")
    for name in ("card0-DP-1", "card0-HDMI-A-1", "renderD128", "card0-eDP-1-bad"):
        assert not _CARD_RE.match(name)


def test_smart_health_from_bool_not_str():
    # 回归锁：旧实现 str(True) 查 "PASSED" 键表恒 unknown，故障 NVMe 被兜底翻 passed
    assert _health_of({"smart_status": {"passed": True}}) == "passed"
    assert _health_of({"smart_status": {"passed": False}}) == "failing"
    assert _health_of({"nvme_smart_health_information_log": {"critical_warning": 0}}) == "unknown"
    assert _health_of({}) == "unknown"


def test_disk_health_cached_with_temps(monkeypatch):
    async def fake_run_cmd(*args, **kw):
        payload = {
            "temperature": {"current": 38},
            "smart_status": {"passed": args[-1] == "/dev/sda"},
        }
        return (0, json.dumps(payload), "")

    monkeypatch.setattr(temperature, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(temperature, "glob", SimpleNamespace(glob=lambda p: ["/dev/sda", "/dev/sdb"]))
    monkeypatch.setattr(temperature.shutil, "which", lambda x: "/usr/sbin/smartctl")
    monkeypatch.setattr(temperature.platform, "system", lambda: "Linux")
    # CI 全新 runner 的 monotonic()（开机秒数）量级不定：ts=0.0 种子可能被 TTL 判为
    # 「缓存仍新鲜」而整体跳过扫描（health 停在种子值）。用远早于当前的过期戳 +
    # 全新缓存对象，测试与运行环境/先后顺序彻底解耦。
    monkeypatch.setattr(
        temperature, "_disk_cache",
        {"ts": temperature.time.monotonic() - 1e6, "items": [], "health": {}, "temps": {}},
    )

    health = asyncio.run(temperature.disk_health())
    assert health == {"sda": "passed", "sdb": "failing"}, (
        f"health={health!r} cache={temperature._disk_cache!r} "
        f"platform={temperature.platform.system()!r} which={temperature.shutil.which('smartctl')!r}"
    )
    # 与盘温共用缓存：60s 内重复调用不再触发探测
    assert asyncio.run(temperature.disk_health()) == health
