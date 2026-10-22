'use strict';

/**
 * 存储域端点（契约 §3.5）：磁盘 / 阵列 / 卷 / SMART 自检。
 */

import { apiData } from '../client';

/** 物理磁盘清单
 * @returns {Promise<import('../../models/storage').DiskItem[]>} */
export function getDisks() {
  return apiData('/api/v1/storage/disks');
}

/** 阵列（硬 RAID + 软 RAID + 控制器 + 物理盘）
 * @returns {Promise<import('../../models/storage').RaidResponse>} */
export function getRaid() {
  return apiData('/api/v1/storage/raid');
}

/** 已挂载存储卷
 * @returns {Promise<import('../../models/storage').VolumeItem[]>} */
export function getVolumes() {
  return apiData('/api/v1/storage/volumes');
}

/** 发起 SMART 自检（同盘互斥，冲突返回 code 1005）
 * @param {string} device 不带 /dev/ 前缀
 * @param {'short'|'long'|'conveyance'} type */
export function startSelfTest(device, type) {
  return apiData('/api/v1/storage/self-tests', { method: 'POST', body: { device, type } });
}

/** 全部自检任务状态
 * @returns {Promise<import('../../models/storage').SelfTestState[]>} */
export function getSelfTests() {
  return apiData('/api/v1/storage/self-tests');
}

/** SMART 指标趋势（smart_15m 每 15 分钟落一桶；days≤30 回 1h 桶，否则 1d 桶）
 * @param {string} device 不带 /dev/ 前缀（nvme0n1 后端自动回退控制器键）
 * @param {string} metric 白名单见契约 §3.2（reallocated/pending/…/power_on_hours）
 * @param {number} days 1-90
 * @returns {Promise<import('../../models/storage').SmartTrendResponse>} */
/** 触发单盘只读跑分（花活二期 Q；写操作后端非 GET 管理员强校验，全局互斥 1005）
 * @param {string} device 盘名（不带 /dev/）
 * @param {number} [seconds] 时长 5-120s
 * @param {number} [duty] IO 占用 10-100%
 * @returns {Promise<import('../../models/storage').BenchState>} */
export function startBenchmark(device, seconds = 20, duty = 30) {
  return apiData('/api/v1/storage/benchmarks', {
    method: 'POST',
    body: JSON.stringify({ device, seconds, duty }),
  });
}

/** 跑分成绩榜（新→旧；device 过滤做同盘历史对比）
 * @param {string} [device]
 * @returns {Promise<import('../../models/storage').BenchResultItem[]>} */
export function getBenchHistory(device) {
  return apiData(
    `/api/v1/storage/benchmarks${device ? `?device=${encodeURIComponent(device)}` : ''}`
  );
}

/** 跑分实时状态（1s 轮询）
 * @returns {Promise<import('../../models/storage').BenchState>} */
export function getBenchCurrent() {
  return apiData('/api/v1/storage/benchmarks/current');
}

/** 取消当前跑分（协作式收尾，部分成绩有效）
 * @returns {Promise<import('../../models/storage').BenchState>} */
export function cancelBenchmark() {
  return apiData('/api/v1/storage/benchmarks/current', { method: 'DELETE' });
}

export function getSmartTrend(device, metric, days = 30) {
  const q = `device=${encodeURIComponent(device)}&metric=${encodeURIComponent(metric)}&days=${days}`;
  return apiData(`/api/v1/storage/trend?${q}`);
}
