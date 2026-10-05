"""配置备份/恢复（M3.5）：用户可编辑数据整体导出/导入 JSON。

范围（全部为用户配置，不含采集数据/事件流）：风扇控区+曲线、告警规则+渠道、
磁盘别名、端口标注、终止保护名单、系统设置（fan_schedule/selftest_schedule）。
渠道凭据默认脱敏导出（备份可分享），include_secrets=True 才带明文——仅管理员
POST 路径可达（trim 路由级鉴权对非 GET 强校验）。导入为 replace-all 整事务
（schema_version 校验前置，不匹配拒绝），开发期无 Alembic 的兜底迁移手段。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidParamsError
from app.models.alert import AlertChannel, AlertRule
from app.models.control import FanCurve, FanZone
from app.models.storage import DiskAlias
from app.models.system import KillWhitelist, PortAlias, SystemSetting
from app.services.alert.channels.base import mask_config

SCHEMA_VERSION = 1
# 可备份的系统设置键（白名单：不带走一次性迁移标记等内部键）
_SETTING_KEYS = ("fan_schedule", "selftest_schedule")


async def export_config(db: AsyncSession, include_secrets: bool = False) -> dict:
    """导出全部用户配置为可导入 JSON。

    Args:
        db (AsyncSession): 请求级会话。
        include_secrets (bool): True 时渠道 config 带明文凭据（备份归档用）；
            False 脱敏导出（可分享，导入后需重新填凭据）。

    Returns:
        dict: {schema_version, exported_at, <各表数组>, settings}。
    """
    async def rows(model, *, order_by=None):
        result = await db.execute(select(model).order_by(*order_by) if order_by else select(model))
        return [c for c in result.scalars()]

    fans = []
    for z in await rows(FanZone):
        fans.append({c.name: getattr(z, c.name) for c in z.__table__.columns})

    curves = []
    for c in await rows(FanCurve):
        curves.append({col.name: getattr(c, col.name) for col in c.__table__.columns})

    rules = []
    for r in await rows(AlertRule):
        rules.append({c.name: getattr(r, c.name) for c in r.__table__.columns})

    channels = []
    for ch in await rows(AlertChannel):
        config = dict(ch.config)
        if not include_secrets:
            config = mask_config(ch.type, config)
        channels.append({
            "id": ch.id,  # 原始 id：导入时重映射规则 channel_ids 的锚点
            "name": ch.name, "type": ch.type, "enabled": ch.enabled,
            "config": config, "config_is_masked": not include_secrets,
        })

    aliases = [{"serial": a.serial, "alias": a.alias} for a in await rows(DiskAlias)]
    ports = [{"port": p.port, "label": p.label, "note": p.note} for p in await rows(PortAlias)]
    whitelist = [{"name": w.name, "reason": w.reason} for w in await rows(KillWhitelist)]

    settings = {}
    for key in _SETTING_KEYS:
        row = await db.get(SystemSetting, key)
        if row is not None:
            settings[key] = row.value

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "fan_zones": fans,
        "fan_curves": curves,
        "alert_rules": rules,
        "alert_channels": channels,
        "disk_aliases": aliases,
        "port_aliases": ports,
        "kill_whitelist": whitelist,
        "settings": settings,
    }


async def import_config(db: AsyncSession, payload: dict) -> dict:
    """整包导入（replace-all，单事务）：先校验 schema 版本再清表重灌。

    Args:
        db (AsyncSession): 请求级会话（get_db 统一 commit，异常整体回滚）。
        payload (dict): export_config 输出。

    Returns:
        dict: 各表导入计数（导入后回读校验用）。

    Raises:
        InvalidParamsError: schema_version 缺失或不被支持。
    """
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise InvalidParamsError(f"不支持的备份 schema_version: {version}（当前支持 {SCHEMA_VERSION}）")

    # 清空（顺序无外键依赖；SQLite 外键默认未启用）
    for model in (FanZone, FanCurve, AlertRule, AlertChannel, DiskAlias, PortAlias, KillWhitelist):
        await db.execute(delete(model))

    counts = {}
    await db.flush()

    # 曲线先灌：old id → new id 映射（控区 curve_id 引用重定向）
    curve_map: dict[int, int] = {}
    for curve in payload.get("fan_curves", []):
        cols = set(FanCurve.__table__.columns.keys()) - {"id", "created_at"}
        obj = FanCurve(**{k: v for k, v in curve.items() if k in cols})
        db.add(obj)
        await db.flush()
        curve_map[curve["id"]] = obj.id
    counts["fan_curves"] = len(curve_map)

    for zone in payload.get("fan_zones", []):
        cols = set(FanZone.__table__.columns.keys()) - {"id", "created_at"}
        zone = {k: v for k, v in zone.items() if k in cols}
        zone["curve_id"] = curve_map.get(zone.get("curve_id"))  # 悬空引用 → None（宁缺勿错）
        db.add(FanZone(**zone))
    counts["fan_zones"] = len(payload.get("fan_zones", []))

    # 渠道先灌：old id → new id 映射（规则 channel_ids 引用重定向）
    channel_map: dict[int, int] = {}
    for ch in payload.get("alert_channels", []):
        config = dict(ch.get("config") or {})
        # 带掩码值导入会把 "****" 写成真凭据——掩码导出形态下剔除 config，留待用户补填
        if ch.get("config_is_masked"):
            config = {}
        obj = AlertChannel(name=ch.get("name", ""), type=ch.get("type", "telegram"),
                           enabled=bool(ch.get("enabled", True)), config=config)
        db.add(obj)
        await db.flush()
        if ch.get("id") is not None:
            channel_map[ch["id"]] = obj.id
    counts["alert_channels"] = len(channel_map)

    for rule in payload.get("alert_rules", []):
        cols = set(AlertRule.__table__.columns.keys()) - {"id", "created_at"}
        rule = {k: v for k, v in rule.items() if k in cols}
        # channel_ids 重映射；渠道被删/缺失的引用直接剔除（不保留悬空）
        rule["channels"] = [channel_map[cid] for cid in rule.get("channels") or [] if cid in channel_map]
        db.add(AlertRule(**rule))
    counts["alert_rules"] = len(payload.get("alert_rules", []))

    for a in payload.get("disk_aliases", []):
        db.add(DiskAlias(serial=a["serial"], alias=a["alias"]))
    for p in payload.get("port_aliases", []):
        db.add(PortAlias(port=p["port"], label=p["label"], note=p.get("note", "")))
    for w in payload.get("kill_whitelist", []):
        db.add(KillWhitelist(name=w["name"], reason=w.get("reason")))
    counts["aliases"] = len(payload.get("disk_aliases", [])) + len(payload.get("port_aliases", [])) + len(
        payload.get("kill_whitelist", [])
    )

    for key, value in (payload.get("settings") or {}).items():
        if key in _SETTING_KEYS:
            row = await db.get(SystemSetting, key)
            if row:
                row.value = value
            else:
                db.add(SystemSetting(key=key, value=value, description="配置备份导入"))
    await db.flush()
    return counts
