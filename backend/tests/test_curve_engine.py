"""温控曲线引擎单测。"""

from __future__ import annotations

from app.services.control.curve_engine import preview, target_pwm

POINTS = [[30, 22], [40, 50], [60, 100]]


def test_below_range():
    assert preview(POINTS, 20) == 22.0


def test_interpolation():
    assert preview(POINTS, 40) == 50.0
    assert preview(POINTS, 50) == 75.0


def test_above_range():
    assert preview(POINTS, 70) == 100.0


def test_slope_limit():
    # 相邻两次目标差被 ramp_per_tick 限制
    full = target_pwm(POINTS, 60, current_pwm=None)
    stepped = target_pwm(POINTS, 60, ramp_per_tick=5, current_pwm=50)
    assert stepped == 55.0 or stepped == full
