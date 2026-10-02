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
    # 回归锁：斜率限制（PWM 防突变，安全相关）必须真实生效——
    # 旧断言 `== 55.0 or == full` 在限幅逻辑被删时照样绿
    stepped = target_pwm(POINTS, 60, ramp_per_tick=5, current_pwm=50)
    assert stepped == 55.0  # 目标 100，单 tick 只能 +5
    assert target_pwm(POINTS, 60, ramp_per_tick=5, current_pwm=90) == 95.0
    # 40°C 曲线目标 50：从 80 下调单 tick 只能 -5
    assert target_pwm(POINTS, 40, ramp_per_tick=5, current_pwm=80) == 75.0
