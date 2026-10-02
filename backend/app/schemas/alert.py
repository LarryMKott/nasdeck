"""告警域 DTO：规则 / 渠道 / 事件（契约 §2.19）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlertRuleIn(BaseModel):
    # 禁 CRLF：规则名会拼进邮件 Subject（头注入）与 Bark URL 路径（定界符截断）
    name: str = Field(min_length=1, max_length=64, pattern=r"^[^\r\n]+$")
    metric: str = Field(pattern="^(cpu_percent|mem_percent|temp_max|disk_temp|disk_failed|raid_degraded)$")
    comparator: str = Field(pattern="^(>|<|>=|<=|==)$")
    threshold: float
    duration_ticks: int = Field(default=1, ge=1, le=1440)
    severity: str = Field(default="warning", pattern="^(info|warning|critical)$")
    channel_ids: list[int] = []
    enabled: bool = True


class AlertRuleItem(AlertRuleIn):
    id: int


class AlertChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: str = Field(pattern="^(telegram|bark|email|webhook)$")
    config: dict
    enabled: bool = True


class AlertChannelItem(BaseModel):
    id: int
    name: str
    type: str
    enabled: bool
    config_masked: dict


class AlertEventItem(BaseModel):
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
    channel_id: int
    success: bool
