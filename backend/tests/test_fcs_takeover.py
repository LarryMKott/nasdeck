"""FCS 安全接管测试（T1，此前全模块零覆盖）：takeover/release 的 rc 逐条校验、
状态落盘、非 fnOS 安全分支与 load_state 落盘对账（T4）。

用假 run_cmd 全离线覆盖命令编排：stop/disable 任一失败都不得翻转状态——
否则原生 FCS 实际仍在运行而 status() 谎报已接管。"""

from __future__ import annotations

import json

import pytest

from app.services.control import fcs_safe_takeover as fcs


@pytest.fixture(autouse=True)
def reset_state():
    """进程内接管状态对齐默认值：用例间互不污染。"""
    fcs._state.update(taken_over=False, enabled_config=False)
    yield
    fcs._state.update(taken_over=False, enabled_config=False)


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    """状态文件指向 tmp_path：不读写真实 data/ 目录。"""
    path = tmp_path / "fcs_state.json"
    monkeypatch.setattr(fcs, "_STATE_FILE", path)
    return path


def _fake_fnos(monkeypatch, on: bool = True) -> None:
    monkeypatch.setattr(fcs, "is_fnos", lambda: on)
    if on:  # fnOS 分支还要求 Linux 才执行 systemctl
        monkeypatch.setattr(fcs.platform, "system", lambda: "Linux")


def _install_run_cmd(monkeypatch, rc_by_verb: dict[str, int]) -> list[tuple]:
    """假 run_cmd：按 systemctl 子命令动词返回 rc 并记录调用序列（非零 rc 附带 stderr）。"""
    calls: list[tuple] = []

    async def _fake(*args, **kwargs):
        calls.append(args)
        verb = args[1] if len(args) > 1 else ""
        rc = rc_by_verb.get(verb, 0)
        return rc, "", "boom" if rc != 0 else ""

    monkeypatch.setattr(fcs, "run_cmd", _fake)
    return calls


# ---------------- takeover：stop/disable 必须逐条确认成功 ----------------


async def test_takeover_success_flips_state_and_persists(state_file, monkeypatch):
    _fake_fnos(monkeypatch)
    calls = _install_run_cmd(monkeypatch, {})

    result = await fcs.takeover()

    assert result == {"taken_over": True}
    assert calls == [("systemctl", "stop", "pwm-fancontrol"), ("systemctl", "disable", "pwm-fancontrol")]
    assert json.loads(state_file.read_text("utf-8")) == {"taken_over": True, "enabled_config": True}
    status = await fcs.status()
    assert status["taken_over"] is True
    assert status["enabled_config"] is True


async def test_takeover_stop_failure_keeps_state(state_file, monkeypatch):
    """stop 失败：不翻转状态、不落盘、不再执行 disable。"""
    _fake_fnos(monkeypatch)
    calls = _install_run_cmd(monkeypatch, {"stop": 1})

    result = await fcs.takeover()

    assert result["taken_over"] is False
    assert "stop" in result["reason"]
    assert calls == [("systemctl", "stop", "pwm-fancontrol")]
    assert not state_file.exists()
    assert (await fcs.status())["taken_over"] is False


async def test_takeover_disable_failure_keeps_state(state_file, monkeypatch):
    """disable 失败：stop 已成功也不得翻转状态（原生 FCS 仍会开机自启）。"""
    _fake_fnos(monkeypatch)
    calls = _install_run_cmd(monkeypatch, {"disable": 1})

    result = await fcs.takeover()

    assert result["taken_over"] is False
    assert "disable" in result["reason"]
    assert [c[1] for c in calls] == ["stop", "disable"]
    assert not state_file.exists()


# ---------------- release：确认成功才翻转状态 ----------------


async def test_release_success_resets_state(state_file, monkeypatch):
    _fake_fnos(monkeypatch)
    calls = _install_run_cmd(monkeypatch, {})

    result = await fcs.release()

    assert result == {"released": True}
    assert calls == [("systemctl", "enable", "--now", "pwm-fancontrol")]
    assert json.loads(state_file.read_text("utf-8")) == {"taken_over": False, "enabled_config": False}


async def test_release_failure_keeps_taken_over(state_file, monkeypatch):
    _fake_fnos(monkeypatch)
    _install_run_cmd(monkeypatch, {"enable": 1})

    result = await fcs.release()

    assert result["released"] is False
    assert "reason" in result
    assert not state_file.exists()


# ---------------- 非 fnOS：安全分支，绝不执行 systemctl ----------------


async def test_takeover_release_noop_without_fnos(state_file, monkeypatch):
    """非 fnOS（含开发机 Windows）：返回 reason 不抛错、不执行命令、不落盘。"""
    _fake_fnos(monkeypatch, on=False)
    calls = _install_run_cmd(monkeypatch, {})

    take = await fcs.takeover()
    release = await fcs.release()

    assert take == {"taken_over": False, "reason": "非 fnOS 环境，无需接管"}
    assert release["released"] is False
    assert release["reason"]
    assert calls == []
    assert not state_file.exists()


# ---------------- load_state：崩溃/升级重启后的落盘对账 ----------------


async def test_load_state_missing_or_corrupt_keeps_default(state_file):
    """无文件/损坏 JSON 均不抛错、状态维持默认（Windows 上 is_fnos=False、active=None 属正常分支）。"""
    assert not state_file.exists()
    fcs.load_state()  # 无状态文件：从未接管过
    status = await fcs.status()
    assert status["taken_over"] is False
    assert status["enabled_config"] is False

    state_file.write_text("{not json", "utf-8")
    fcs.load_state()  # 损坏 JSON：吞 ValueError，状态维持默认
    status = await fcs.status()
    assert status["taken_over"] is False


async def test_load_state_recovers_taken_over(state_file):
    """SIGKILL 后重启：落盘的接管状态必须如实上报，不得谎报未接管。"""
    state_file.write_text(json.dumps({"taken_over": True, "enabled_config": True}), "utf-8")

    fcs.load_state()

    status = await fcs.status()
    assert status["taken_over"] is True
    assert status["enabled_config"] is True
    assert status["unit"] == "pwm-fancontrol"
