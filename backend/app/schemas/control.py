"""控制域 DTO：hwmon 通道 / 风扇控区 / 温控曲线 / FCS（契约 §2.15-2.18）。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class HwmonChannel(BaseModel):
    """hwmon 可控通道探查结果。"""
    chip: str
    chip_path: str
    pwm_channel: int
    fan_channel: int | None = None
    label: str | None = None
    current_pwm_pct: float | None = None
    current_rpm: int | None = None
    pwm_enable: int | None = None
    writable: bool


class FanZoneIn(BaseModel):
    """风扇控区创建请求体（契约 §2.17/§3.4）。"""
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
    """控区局部更新请求体（任意子集，显式 null 清除可空字段）。"""
    name: str | None = Field(default=None, min_length=1, max_length=64)
    mode: str | None = Field(default=None, pattern="^(auto|curve|fixed)$")
    fixed_pwm: int | None = Field(default=None, ge=0, le=100)
    curve_id: int | None = None
    enabled: bool | None = None
    sensor_key: str | None = None


class FanZoneItem(BaseModel):
    """风扇控区响应体（含实时转速/占空比）。"""
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
    """温控曲线创建请求体。"""
    name: str = Field(min_length=1, max_length=64)
    points: list[list[float]] = Field(min_length=2)
    hysteresis_c: float = Field(default=2, ge=0, le=10)
    ramp_per_tick: float = Field(default=5, ge=1, le=50)

    @model_validator(mode="after")
    def check_points(self) -> CurveIn:
        """校验曲线点形状/占空比范围/温度严格递增。

        Returns:
            CurveIn: 校验通过的原模型。

        Raises:
            ValueError: 点非 [temp, pwm] 二元组、占空比越界或温度非严格递增
                （Pydantic 转信封 2000；先验形状再取下标，避免 IndexError）。
        """
        # 先验形状再取下标：畸形单点（如 []）应返回 422 校验错误而非 IndexError
        if any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in self.points):
            raise ValueError("每个点必须是 [temp, pwm] 二元组")
        temps = [p[0] for p in self.points]
        if any(not (0 <= p[1] <= 100) for p in self.points):
            raise ValueError("占空比必须在 0-100")
        if any(b <= a for a, b in zip(temps, temps[1:], strict=False)):
            raise ValueError("温度必须严格递增")
        self.points = sorted(self.points, key=lambda p: p[0])
        return self


class CurveItem(CurveIn):
    """温控曲线（含 id）。"""
    id: int


class FcsStatus(BaseModel):
    """风扇接管服务状态。"""
    is_fnos: bool
    unit: str = "pwm-fancontrol"
    active: bool | None  # 非 Linux 为 null
    taken_over: bool
    enabled_config: bool

class FanScheduleIn(BaseModel):
    """时段静音计划（M2.5）：窗口期内曲线评估温度平移 -offset_c（更静）。"""
    """时段静音计划（M2.5）：窗口期内曲线评估温度平移 -offset_c（更静）。"""

    enabled: bool
    start: int = Field(ge=0, le=23)
    end: int = Field(ge=0, le=23)
    offset_c: float = Field(ge=0, le=15)


class FanScheduleOut(FanScheduleIn):
    """时段静音计划响应（含 active 实时判定）。"""
    active: bool = False  # 当前时刻是否处于静音窗口（响应时实时判定）
