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

/** 网络星图数据面（花活二期 L）：LISTEN/ESTABLISHED 聚合 + 远端内网外网归类
 * @returns {Promise<import('../../models/system').NetworkMap>} */
export function getNetworkMap() {
  return apiData('/api/v1/system/network/map');
}

/** 单容器资源趋势（1m 桶，花活二期 M）
 * @param {string} name 容器名
 * @param {number} hours 回看小时数 1-168
 * @returns {Promise<import('../../models/system').ContainerTrendResponse>} */
export function getContainerTrend(name, hours = 24) {
  return apiData(
    `/api/v1/system/docker/containers/${encodeURIComponent(name)}/trend?hours=${hours}`
  );
}

/** 容器生命周期控制：start/stop/restart（写操作，后端非 GET 管理员强校验；花活二期 M）
 * @param {string} name 容器名
 * @param {'start'|'stop'|'restart'} action
 * @returns {Promise<{name: string, action: string, ok: boolean}>} */
export function controlContainer(name, action) {
  return apiData(`/api/v1/system/docker/containers/${encodeURIComponent(name)}/${action}`, {
    method: 'POST',
  });
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

/** SMART 周期巡检计划
 * @returns {Promise<import('../../models/system').SelftestSchedule>} */
export function getSelftestSchedule() {
  return apiData('/api/v1/system/selftest-schedule');
}

/** 保存巡检计划（仅管理员；PUT 由后端 trim 鉴权强校验）
 * @param {import('../../models/system').SelftestSchedule} cfg */
export function putSelftestSchedule(cfg) {
  return apiData('/api/v1/system/selftest-schedule', {
    method: 'PUT',
    body: { enabled: cfg.enabled, weekday: cfg.weekday, hour: cfg.hour, type: cfg.type },
  });
}

/** 导出用户配置备份（POST 动词语义：仅管理员；include_secrets 带明文凭据）
 * @param {boolean} [includeSecrets]
 * @returns {Promise<object>} 备份 JSON（schema_version 锚定导入兼容性） */
export function exportConfigBackup(includeSecrets = false) {
  return apiData('/api/v1/system/config-export', {
    method: 'POST',
    body: { include_secrets: includeSecrets },
  });
}

/** 导入配置备份（replace-all 单事务；schema_version 不匹配整体拒绝）
 * @param {object} payload 备份 JSON
 * @returns {Promise<object>} 各表导入计数 */
export function importConfigBackup(payload) {
  return apiData('/api/v1/system/config-import', { method: 'POST', body: payload });
}

/** 周报推送计划
 * @returns {Promise<import('../../models/system').ReportSchedule>} */
export function getReportSchedule() {
  return apiData('/api/v1/system/report-schedule');
}

/** 保存周报推送计划（仅管理员）
 * @param {import('../../models/system').ReportSchedule} cfg */
export function putReportSchedule(cfg) {
  return apiData('/api/v1/system/report-schedule', {
    method: 'PUT',
    body: { enabled: cfg.enabled, weekday: cfg.weekday, hour: cfg.hour },
  });
}

/** 立即生成并广播周报（调试/验收；仅管理员）
 * @returns {Promise<{digest: string}>} */
export function sendReportNow() {
  return apiData('/api/v1/system/report/send', { method: 'POST', body: {} });
}
