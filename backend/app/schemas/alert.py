"""告警域 DTO：规则 / 渠道 / 事件（契约 §2.19）。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# smart_rate:<指标> 与 capacity_forecast 为慢速规则（smart_15m / volume_15m 驱动评估），
# 阈值规则 6 项由 medium_5s 实时评估
_METRIC_PATTERN = (
    "^(cpu_percent|mem_percent|temp_max|disk_temp|disk_failed|raid_degraded"
    "|capacity_forecast"
    "|smart_rate:(reallocated|pending|uncorrectable|wear_leveling"
    "|percent_used|media_errors|temp_c|power_on_hours))$"
)

# 与 engine.VALID_ACTIONS 一致（此处独立声明避免 schemas→services 反向依赖）
_ACTION_VALUES = ("fan_full", "report")


class AlertRuleIn(BaseModel):
    """告警规则创建/更新请求体（契约 §2.19）。"""
    # 禁 CRLF：规则名会拼进邮件 Subject（头注入）与 Bark URL 路径（定界符截断）
    name: str = Field(min_length=1, max_length=64, pattern=r"^[^\r\n]+$")
    metric: str = Field(pattern=_METRIC_PATTERN)
    comparator: str = Field(pattern="^(>|<|>=|<=|==)$")
    threshold: float
    duration_ticks: int = Field(default=1, ge=1, le=1440)
    severity: str = Field(default="warning", pattern="^(info|warning|critical)$")
    channel_ids: list[int] = []
    # 剧本动作（M2.1）：fan_full=风扇全速 15 分钟 / report=生成诊断报告（脱敏）
    actions: list[str] = []

    @field_validator("actions")
    @classmethod
    def _actions_whitelist(cls, v: list[str]) -> list[str]:
        """校验剧本动作白名单（与 engine.VALID_ACTIONS 一致，独立声明避免反向依赖）。

        Args:
            v (list[str]): 动作名列表。

        Returns:
            list[str]: 原样返回（校验通过）。

        Raises:
            ValueError: 含白名单外动作名。
        """
        if any(a not in _ACTION_VALUES for a in v):
            raise ValueError(f"actions 仅支持 {'/'.join(_ACTION_VALUES)}")
        return v

    enabled: bool = True


class AlertRuleItem(AlertRuleIn):
    """告警规则响应体（含 id）。"""
    id: int


class AlertChannelIn(BaseModel):
    """通知渠道创建/更新请求体（config 明文，仅写接口）。"""
    name: str = Field(min_length=1, max_length=64)
    type: str = Field(pattern="^(telegram|bark|email|webhook)$")
    config: dict
    enabled: bool = True


class AlertChannelItem(BaseModel):
    """通知渠道响应体（config 脱敏为 config_masked）。"""
    id: int
    name: str
    type: str
    enabled: bool
    config_masked: dict


class AlertEventItem(BaseModel):
    """告警/系统事件响应体。"""
    id: int
    rule_id: int | None
    rule_name: str
    metric: str
    value: float | None
    threshold: float | None
    severity: str
    status: str
    message: str | None
    fired_at: str
    resolved_at: str | None


class ChannelTestResult(BaseModel):
    """渠道连通性测试结果。"""
    channel_id: int
    success: bool
