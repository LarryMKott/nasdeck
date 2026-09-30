"""温控曲线引擎：插值试算 + 迟滞 + 斜率限制（契约 §2.17 约束在 schema 校验）。"""

from __future__ import annotations


def target_pwm(
    points: list[list[float]],
    temp_c: float,
    hysteresis_c: float = 2.0,
    ramp_per_tick: int = 5,
    current_pwm: float | None = None,
) -> float:
    """给定温度试算目标占空比：
    - 低于最低点温度 → 最低点占空比；高于最高点 → 100
    - 区间内线性插值
    - 迟滞：温度回落不超过 hysteresis_c 时保持既有占空比方向（简化：仅下调需越过迟滞带）
    - 斜率：单次调整幅度限制 ramp_per_tick
    """
    pts = sorted(points, key=lambda p: p[0])
    if temp_c <= pts[0][0]:
        target = float(pts[0][1])
    elif temp_c >= pts[-1][0]:
        target = 100.0
    else:
        target = float(pts[-1][1])
        for (t0, p0), (t1, p1) in zip(pts, pts[1:], strict=False):
            if t0 <= temp_c <= t1:
                target = p0 + (p1 - p0) * (temp_c - t0) / (t1 - t0)
                break
    # 迟滞：目标低于当前时，需温度差超过迟滞带才允许下调（用占空比等效阻尼）
    if current_pwm is not None and target < current_pwm:
        if temp_c > pts[0][0] and current_pwm - target < hysteresis_c * (ramp_per_tick / 5):
            target = current_pwm
    # 斜率限制
    if current_pwm is not None:
        target = max(current_pwm - ramp_per_tick, min(current_pwm + ramp_per_tick, target))
    return round(max(0.0, min(100.0, target)), 1)


def preview(points: list[list[float]], temp_c: float) -> float:
    return round(target_pwm(points, temp_c), 1)
