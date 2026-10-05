'use strict';

/**
 * 告警域数据模型（对齐 backend/app/schemas/alert.py，契约 §2.19）。
 */

/** @typedef {'cpu_percent'|'mem_percent'|'temp_max'|'disk_temp'|'disk_failed'|'raid_degraded'} AlertMetric */

/** @typedef {'>'|'<'|'>='|'<='|'=='} AlertComparator */

/** @typedef {'info'|'warning'|'critical'} AlertSeverity */

/** @typedef {'telegram'|'bark'|'email'|'webhook'} AlertChannelType */

/** 创建告警规则请求体（POST /alert/rules；name 禁 CRLF——会拼进邮件 Subject/Bark URL）
 * @typedef {object} AlertRuleIn
 * @property {AlertMetric} metric
 * @property {string} name
 * @property {AlertComparator} comparator
 * @property {number} threshold
 * @property {number} [duration_ticks]
 * @property {AlertSeverity} [severity]
 * @property {number[]} [channel_ids]
 * @property {Array<'fan_full'|'report'>} [actions] 触发后剧本动作
 * @property {boolean} [enabled]
 */

/** 告警规则（GET /alert/rules）
 * @typedef {object} AlertRuleItem
 * @property {number} id
 * @property {string} name
 * @property {AlertMetric} metric
 * @property {AlertComparator} comparator
 * @property {number} threshold
 * @property {number} duration_ticks
 * @property {AlertSeverity} severity
 * @property {number[]} channel_ids
 * @property {Array<'fan_full'|'report'>} actions
 * @property {boolean} enabled
 */

/** 创建通知渠道请求体（POST /alert/channels）
 * @typedef {object} AlertChannelIn
 * @property {string} name
 * @property {AlertChannelType} type
 * @property {Record<string, unknown>} config
 * @property {boolean} [enabled]
 */

/** 通知渠道（GET /alert/channels；config 掩码回显）
 * @typedef {object} AlertChannelItem
 * @property {number} id
 * @property {string} name
 * @property {AlertChannelType} type
 * @property {boolean} enabled
 * @property {Record<string, unknown>} config_masked
 */

/** 告警事件（GET /alert/events；总览告警卡/布局铃铛/自动化日志共用）
 * @typedef {object} AlertEventItem
 * @property {number} id
 * @property {number|null} rule_id
 * @property {string} rule_name
 * @property {AlertMetric} metric
 * @property {number|null} value
 * @property {number|null} threshold
 * @property {AlertSeverity} severity
 * @property {string} status
 * @property {string|null} message
 * @property {string} fired_at
 * @property {string|null} resolved_at
 */

/** 渠道测试结果（POST /alert/channels/{id}/test）
 * @typedef {object} ChannelTestResult
 * @property {number} channel_id
 * @property {boolean} success
 */

/** 健康报告生成结果（POST /report/health，无 schema 端点）
 * @typedef {object} HealthReportResult
 * @property {string} url 根相对路径 /api/v1/...，FPK 形态须拼 index.cgi 前缀
 * @property {string} [filename]
 */

export {};
