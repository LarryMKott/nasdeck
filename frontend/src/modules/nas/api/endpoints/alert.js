'use strict';

/**
 * 告警域端点（契约 §3.19）：事件 / 规则 / 渠道。
 */

import { apiData } from '../client';

// firing 告警 30s 请求级缓存：进总览一次有 fetchDashboard / 告警卡 / 布局铃铛三处同 URL 请求
let _firingEvents = { ts: 0, data: null };

/** firing 告警（30s 缓存；空列表 = 无告警，是合法真值）
 * @returns {Promise<import('../../models/alert').AlertEventItem[]>} */
export async function getFiringEvents() {
  const now = Date.now();
  if (_firingEvents.data && now - _firingEvents.ts < 30000) return _firingEvents.data;
  const data = await apiData('/api/v1/alert/events?limit=5&status=firing');
  _firingEvents = { ts: now, data };
  return data;
}

/** 告警事件流（自动化页日志/错误历史数据源）
 * @param {number} [limit]
 * @returns {Promise<import('../../models/alert').AlertEventItem[]>} */
export function getEvents(limit, source = 'all') {
  return apiData(`/api/v1/alert/events?limit=${limit ?? 10}&source=${source}`);
}

/** 告警规则清单
 * @returns {Promise<import('../../models/alert').AlertRuleItem[]>} */
export function getRules() {
  return apiData('/api/v1/alert/rules');
}

/** 创建告警规则
 * @param {import('../../models/alert').AlertRuleIn} body */
export function createRule(body) {
  return apiData('/api/v1/alert/rules', { method: 'POST', body });
}

/** 更新告警规则（全量更新：未传字段会被后端重置为默认值）
 * @param {number} ruleId
 * @param {import('../../models/alert').AlertRuleIn} body */
export function updateRule(ruleId, body) {
  return apiData(`/api/v1/alert/rules/${ruleId}`, { method: 'PUT', body });
}

/** 删除告警规则
 * @param {number} ruleId */
export function deleteRule(ruleId) {
  return apiData(`/api/v1/alert/rules/${ruleId}`, { method: 'DELETE' });
}

/** 通知渠道清单（config 脱敏回显）
 * @returns {Promise<import('../../models/alert').AlertChannelItem[]>} */
export function getChannels() {
  return apiData('/api/v1/alert/channels');
}

/** 创建通知渠道
 * @param {import('../../models/alert').AlertChannelIn} body */
export function createChannel(body) {
  return apiData('/api/v1/alert/channels', { method: 'POST', body });
}

/** 更新通知渠道（config 中仍带掩码 **** 的字段由后端合并回旧值）
 * @param {number} channelId
 * @param {import('../../models/alert').AlertChannelIn} body */
export function updateChannel(channelId, body) {
  return apiData(`/api/v1/alert/channels/${channelId}`, { method: 'PUT', body });
}

/** 删除通知渠道
 * @param {number} channelId */
export function deleteChannel(channelId) {
  return apiData(`/api/v1/alert/channels/${channelId}`, { method: 'DELETE' });
}

/** 发送测试通知
 * @param {number} channelId
 * @returns {Promise<import('../../models/alert').ChannelTestResult>} */
export function testChannel(channelId) {
  return apiData(`/api/v1/alert/channels/${channelId}/test`, { method: 'POST' });
}
