"""告警域模型：规则、通知渠道（config 明文入库，读接口脱敏）、事件。"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AlertRule(Base, TimestampMixin):
    """告警规则：阈值（5s 轮）与慢速（smart_rate/capacity，15 分钟轮）统一载体。

    Attributes:
        metric (str): 指标名，枚举见契约 §2.19（含 smart_rate:<指标> / capacity_forecast）。
        duration_ticks (int): 连续满足次数（1-1440；tick 长度随规则类型）。
        channels (list): 通知渠道 id 列表（触发时逐渠道推送）。
        actions (list): 剧本动作（fan_full / report，见 engine.VALID_ACTIONS）。
    """

    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    # cpu_percent/mem_percent/temp_max/disk_temp/disk_failed/raid_degraded
    metric: Mapped[str] = mapped_column(String(32))
    comparator: Mapped[str] = mapped_column(String(2))  # > < >= <= ==
    threshold: Mapped[float] = mapped_column(Float)
    duration_ticks: Mapped[int] = mapped_column(Integer, default=1)  # 1-1440 连续满足次数
    severity: Mapped[str] = mapped_column(String(8), default="warning")  # info/warning/critical
    channels: Mapped[list] = mapped_column(JSON, default=list)  # channel_id 列表
    # 剧本动作（M2.1 IF-THEN）：fan_full=风扇全速 15 分钟 / report=生成诊断报告；
    # 通知推送由 channels 承载，不在 actions 内
    actions: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertChannel(Base, TimestampMixin):
    """通知渠道：Telegram/Bark/邮件/Webhook 任一形态的推送目标。

    Attributes:
        type (str): telegram / bark / email / webhook。
        config (dict): 凭据与参数（明文入库；读接口经 mask_config 脱敏）。
    """

    __tablename__ = "alert_channels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16))  # telegram/bark/email
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # 明文入库，读接口脱敏
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertEvent(Base, TimestampMixin):
    """告警/系统事件：规则触发记录 + 系统级一次性事件（巡检/容器退出/同步等）。

    rule_id 为 null 的事件是系统级一次性记录（落库即 resolved，无 firing 生命周期）。

    Attributes:
        status (str): firing（活跃）/ resolved（已恢复或一次性记录）。
        metric (str): 规则指标或系统事件类型（selftest/docker_exit/raid_sync/...）。
    """

    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    rule_name: Mapped[str] = mapped_column(String(64), default="")
    metric: Mapped[str] = mapped_column(String(32), default="")
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(8), default="warning")
    status: Mapped[str] = mapped_column(String(8), default="firing", index=True)  # firing/resolved
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fired_at: Mapped[str] = mapped_column(String(32), default="")
    resolved_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
