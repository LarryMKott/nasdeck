"""温控曲线引擎：插值试算 + 迟滞 + 斜率限制（契约 §2.17 约束在 schema 校验）。"""

from __future__ import annotations


def target_pwm(
    points: list[list[float]],
    temp_c: float,
    hysteresis_c: float = 2.0,
    ramp_per_tick: int = 5,
    current_pwm: float | None = None,
) -> float:
    """给定温度试算目标占空比（叠加迟滞与单 tick 斜率限制）。

    算法口径：
    - 低于最低点温度 → 最低点占空比；高于最高点 → 100
    - 区间内线性插值
    - 迟滞：温度回落不超过 hysteresis_c 时保持既有占空比方向（简化：仅下调需越过迟滞带）
    - 斜率：单次调整幅度限制 ramp_per_tick

    Args:
        points (list[list[float]]): [温度°C, 占空比%] 二元组列表，内部按温度升序重排。
        temp_c (float): 当前评估温度（°C）。
        hysteresis_c (float): 回差带宽（°C），默认 2.0。
        ramp_per_tick (int): 单次调整占空比最大变化百分点，默认 5。
        current_pwm (float | None): 当前占空比（0-100），迟滞与斜率限制的基准；
            None 表示无基准，两项阻尼均不生效（允许跳变）。默认 None。

    Returns:
        float: 目标占空比（0-100，保留 1 位小数）。

    Raises:
        IndexError: points 为空列表时。
        ValueError: 某个点不是恰好两个数值（解包失败）时。
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
    """预览某温度下的曲线目标占空比（不传当前占空比，无迟滞/斜率阻尼）。

    Args:
        points (list[list[float]]): [温度°C, 占空比%] 二元组列表，按温度升序。
        temp_c (float): 评估温度（°C）。

    Returns:
        float: 预览占空比（0-100，保留 1 位小数）。
    """
    return round(target_pwm(points, temp_c), 1)
