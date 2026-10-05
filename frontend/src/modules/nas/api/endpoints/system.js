'use strict';

/**
 * 系统域端点（契约 §3.4）：主机信息 / 环境自检 / Docker / 端口 / 进程。
 */

import { apiData } from '../client';

// system/info 30s 请求级缓存：总览/关于/硬件检测/identity 四处同 URL 请求，
// SPA 生命周期内主机信息不会分钟级变化，30s 内命中缓存
let _sysInfo = { ts: 0, data: null };

/** 主机信息（identity 权限判定 / 关于页 / 硬件检测共用）
 * @returns {Promise<import('../../models/system').SystemInfo>} */
export async function getSystemInfo() {
  const now = Date.now();
  if (_sysInfo.data && now - _sysInfo.ts < 30000) return _sysInfo.data;
  const data = await apiData('/api/v1/system/info');
  _sysInfo = { ts: now, data };
  return data;
}

/** 运行环境自检（§2.14，无 schema 端点）
 * @returns {Promise<import('../../models/system').EnvCheck>} */
export function getEnv() {
  return apiData('/api/v1/system/env');
}

/** Docker 容器清单
 * @returns {Promise<import('../../models/system').DockerResponse>} */
export function getDocker() {
  return apiData('/api/v1/system/docker/containers');
}

/** 监听/连接端口清单
 * @returns {Promise<import('../../models/system').PortEntry[]>} */
export function getPorts() {
  return apiData('/api/v1/system/ports');
}

/** 终止进程（端口释放；confirm=true 由后端要求，唯一调用场景固定带）
 * @param {number} pid */
export function killProcess(pid) {
  return apiData(`/api/v1/system/processes/${pid}?confirm=true`, { method: 'DELETE' });
}
