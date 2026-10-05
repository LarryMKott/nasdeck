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
