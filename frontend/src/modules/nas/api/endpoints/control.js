'use strict';

/**
 * 控制域端点（契约 §3.15-§3.18）：风扇风区 / 温控曲线 / FCS 接管 / hwmon 通道。
 * 全部写操作（FanView 原内联 7 处 URL）收拢于此。
 */

import { apiData } from '../client';

/** 风区清单
 * @returns {Promise<import('../../models/control').FanZoneItem[]>} */
export function getFans() {
  return apiData('/api/v1/control/fans');
}

/** 创建风区
 * @param {import('../../models/control').FanZoneIn} body */
export function createFan(body) {
  return apiData('/api/v1/control/fans', { method: 'POST', body });
}

/** 更新风区（PWM 开关/滑杆等 patch 语义）
 * @param {number} zoneId
 * @param {import('../../models/control').FanZoneUpdate} patch */
export function updateFan(zoneId, patch) {
  return apiData(`/api/v1/control/fans/${zoneId}`, { method: 'PUT', body: patch });
}

/** 删除风区
 * @param {number} zoneId */
export function deleteFan(zoneId) {
  return apiData(`/api/v1/control/fans/${zoneId}`, { method: 'DELETE' });
}

/** 温控曲线清单
 * @returns {Promise<import('../../models/control').CurveItem[]>} */
export function getCurves() {
  return apiData('/api/v1/control/curves');
}

/** 创建曲线
 * @param {import('../../models/control').CurveIn} body */
export function createCurve(body) {
  return apiData('/api/v1/control/curves', { method: 'POST', body });
}

/** 更新曲线
 * @param {number} curveId
 * @param {import('../../models/control').CurveIn} body */
export function updateCurve(curveId, body) {
  return apiData(`/api/v1/control/curves/${curveId}`, { method: 'PUT', body });
}

/** FCS 接管服务状态
 * @returns {Promise<import('../../models/control').FcsStatus>} */
export function getFcs() {
  return apiData('/api/v1/control/fcs');
}

/** 接管风扇控制（BIOS → nasdeck） */
export function takeoverFcs() {
  return apiData('/api/v1/control/fcs/takeover', { method: 'POST' });
}

/** 交还风扇控制（nasdeck → BIOS） */
export function releaseFcs() {
  return apiData('/api/v1/control/fcs/release', { method: 'POST' });
}

/** 时段静音计划（窗口内曲线目标温度上移，夜间更静）
 * @returns {Promise<import('../../models/control').FanSchedule>} */
export function getFanSchedule() {
  return apiData('/api/v1/control/fan-schedule');
}

/** 保存时段静音计划（仅管理员；≤5s 生效）
 * @param {import('../../models/control').FanSchedule} cfg */
export function putFanSchedule(cfg) {
  return apiData('/api/v1/control/fan-schedule', {
    method: 'PUT',
    body: { enabled: cfg.enabled, start: cfg.start, end: cfg.end, offset_c: cfg.offset_c },
  });
}

/** 未建风区的 hwmon 硬件通道（硬件检测区数据源）
 * @returns {Promise<import('../../models/control').HwmonChannel[]>} */
export function getHwmonChannels() {
  return apiData('/api/v1/control/hwmon/channels');
}
