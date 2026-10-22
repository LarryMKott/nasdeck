'use strict';

/**
 * 监控域端点（契约 §3.1-§3.3）：实时快照 / 温度 / 历史。
 * URL 与查询参数口径（历史 range → minutes/points 映射）唯一定义于此。
 */

import { apiData, apiBase } from '../client';

/** 历史区间 → 采样窗口/点数（fetchHistory 系列共用，消除三处重复映射） */
const HISTORY_RANGES = {
  '24h': { minutes: 1440, points: 144 },
  '7d': { minutes: 10080, points: 168 },
  '30d': { minutes: 43200, points: 360 },
};

/** @param {string} rangeKey '24h'|'7d'|'30d' */
export function historyRange(rangeKey) {
  return HISTORY_RANGES[rangeKey] ?? HISTORY_RANGES['7d'];
}

/** 实时快照（WS 不可达时 2s 轮询降级也走这里）
 * @returns {Promise<import('../../models/monitor').RealtimeSnapshot>} */
export function getRealtime() {
  return apiData('/api/v1/monitor/realtime');
}

/** 全部温度传感器读数
 * @returns {Promise<import('../../models/monitor').TemperatureItem[]>} */
export function getTemperatures() {
  return apiData('/api/v1/monitor/temperatures');
}

/** 一键体检（花活二期 N：六维聚合只读）
 * @returns {Promise<import('../../models/monitor').CheckupResponse>} */
export function getCheckup() {
  return apiData('/api/v1/monitor/checkup');
}

/** 历史序列
 * @param {string} rangeKey '24h'|'7d'|'30d'
 * @returns {Promise<import('../../models/monitor').HistoryResponse>} */
export function getHistory(rangeKey) {
  const { minutes, points } = historyRange(rangeKey);
  return apiData(`/api/v1/monitor/history?minutes=${minutes}&points=${points}`);
}

/** 历史区间统计
 * @param {string} dim cpu|mem|temp|net|disk|gpu
 * @param {string} rangeKey '24h'|'7d'|'30d'
 * @returns {Promise<import('../../models/monitor').HistoryStats>} */
export function getHistoryStats(dim, rangeKey) {
  const { minutes } = historyRange(rangeKey);
  return apiData(`/api/v1/monitor/history/stats?minutes=${minutes}&dim=${dim}`);
}

/** 历史报告导出 URL（§3.1 export 文件流，带网关 index.cgi 前缀可直接下载）
 * @param {string} dim cpu|mem|temp|net|disk|gpu
 * @param {string} rangeKey '24h'|'7d'|'30d'
 * @param {string} fmt 'csv'|'html' */
export function historyExportUrl(dim, rangeKey, fmt) {
  const { minutes } = historyRange(rangeKey);
  return `${apiBase()}/api/v1/monitor/history/export?minutes=${minutes}&dim=${dim}&fmt=${fmt}`;
}
