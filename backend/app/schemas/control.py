"""控制域 DTO：hwmon 通道 / 风扇控区 / 温控曲线 / FCS（契约 §2.15-2.18）。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class HwmonChannel(BaseModel):
    chip: str
    chip_path: str
    pwm_channel: int
    label: str | None = None
    current_pwm_pct: float | None = None
    current_rpm: int | None = None
    pwm_enable: int | None = None
    writable: bool


class FanZoneIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    loop: str = Field(pattern="^(cpu|chassis)$")
    hwmon_name: str
    pwm_channel: int = Field(ge=1, le=16)
    fan_channel: int | None = Field(default=None, ge=1, le=16)
    mode: str = Field(pattern="^(auto|curve|fixed)$")
    fixed_pwm: int = Field(default=50, ge=0, le=100)
    curve_id: int | None = None
    enabled: bool = True
    sensor_key: str | None = None


class FanZoneUpdate(BaseModel):
    mode: str | None = Field(default=None, pattern="^(auto|curve|fixed)$")
    fixed_pwm: int | None = Field(default=None, ge=0, le=100)
    curve_id: int | None = None
    enabled: bool | None = None
    sensor_key: str | None = None


class FanZoneItem(BaseModel):
    id: int
    name: str
    loop: str
    hwmon_name: str
    pwm_channel: int
    mode: str
    fixed_pwm: int
    curve_id: int | None
    enabled: bool
    sensor_key: str | None
    current_pwm_pct: float | None
    current_rpm: int | None
    sensor_temp_c: float | None


class CurveIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    points: list[list[float]] = Field(min_length=2)
    hysteresis_c: float = Field(default=2, ge=0, le=10)
    ramp_per_tick: float = Field(default=5, ge=1, le=50)

    @model_validator(mode="after")
    def check_points(self) -> CurveIn:
        temps = [p[0] for p in self.points]
        if any(len(p) != 2 for p in self.points):
            raise ValueError("每个点必须是 [temp, pwm] 二元组")
        if any(not (0 <= p[1] <= 100) for p in self.points):
            raise ValueError("占空比必须在 0-100")
        if any(b <= a for a, b in zip(temps, temps[1:], strict=False)):
            raise ValueError("温度必须严格递增")
        self.points = sorted(self.points, key=lambda p: p[0])
        return self


class CurveItem(CurveIn):
    id: int


class FcsStatus(BaseModel):
    is_fnos: bool
    unit: str = "pwm-fancontrol"
    active: bool | None  # 非 Linux 为 null
    taken_over: bool
    enabled_config: bool
