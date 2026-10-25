"""控制域模型：风扇控区与温控曲线。"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FanZone(Base, TimestampMixin):
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
    # 绑定到具体 hwmon 实例（/sys/class/hwmon/hwmonN）：同名芯片多实例时
    # 仅按名字+通道号会绑到第一个匹配，想控的风扇没被控（评审 N5/A4）；
    # NULL = 旧数据/单实例，回退按名字定位
    chip_path: Mapped[str | None] = mapped_column(String(128), nullable=True)


class FanCurve(Base, TimestampMixin):
    __tablename__ = "fan_curves"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    points: Mapped[list] = mapped_column(JSON, default=list)  # [[temp_c, pwm_pct], ...] 温度递增
    hysteresis_c: Mapped[float] = mapped_column(Float, default=2)  # 0-10
    ramp_per_tick: Mapped[float] = mapped_column(Float, default=5)  # 1-50
