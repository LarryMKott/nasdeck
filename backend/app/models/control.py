"""控制域模型：风扇控区与温控曲线。"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FanZone(Base, TimestampMixin):
    """风扇控区：一块可写 PWM 通道的调速策略载体（契约 §2.17）。

    Attributes:
        loop (str): 所属回路 cpu / chassis（展示分组）。
        hwmon_name (str): 主板 hwmon 芯片名（写 pwm 定位键）。
        pwm_channel (int): PWM 写通道号（1-16）。
        fan_channel (int | None): 转速计通道号（None = 无转速计）。
        mode (str): auto（BIOS 接管）/ curve（曲线温控）/ fixed（定速）。
        fixed_pwm (int): 定速占空比（0-100）。
        curve_id (int | None): 绑定曲线 id（curve 模式必填）。
        sensor_key (str | None): 调速依据传感器键（None = CPU 最高温）。
    """

    __tablename__ = "fan_zones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    loop: Mapped[str] = mapped_column(String(16))  # cpu / chassis
    hwmon_name: Mapped[str] = mapped_column(String(64))
    pwm_channel: Mapped[int] = mapped_column(Integer)
    fan_channel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(8), default="auto")  # auto / curve / fixed
    fixed_pwm: Mapped[int] = mapped_column(Integer, default=50)  # 0-100
    curve_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sensor_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


class FanCurve(Base, TimestampMixin):
    """温控曲线：「温度 → 占空比」分段线性曲线（契约 §2.17）。

    Attributes:
        points (list): [[温度°C, 占空比%], ...] 温度递增（curve_engine 评估输入）。
        hysteresis_c (float): 迟滞回差（0-10，避免临界抖动）。
        ramp_per_tick (float): 每 tick 最大变化百分点（1-50，转速平滑）。
    """

    __tablename__ = "fan_curves"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    points: Mapped[list] = mapped_column(JSON, default=list)  # [[temp_c, pwm_pct], ...] 温度递增
    hysteresis_c: Mapped[float] = mapped_column(Float, default=2)  # 0-10
    ramp_per_tick: Mapped[float] = mapped_column(Float, default=5)  # 1-50
