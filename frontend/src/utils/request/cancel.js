'use strict';

/**
 * 重复请求自动取消：以「方法 + 地址 + 参数」为唯一标识，
 * 发起相同请求时自动中止前一个未完成的请求（AbortController 实现）。
 */

/** @type {Map<string, AbortController>} pending 请求登记表 */
const pendingMap = new Map();

/**
 * 生成请求唯一标识
 * @param {import('axios').AxiosRequestConfig} [config] 请求配置
 * @returns {string} 请求 key
 */
export function getPendingKey(config = {}) {
  const { method = 'get', url = '', params, data } = config;
  return `${String(method).toLowerCase()}&${url}&${JSON.stringify(params ?? null)}&${JSON.stringify(data ?? null)}`;
}

/**
 * 移除 pending 请求，可选择同时中止
 * @param {import('axios').AxiosRequestConfig} config 请求配置
 * @param {boolean} [abort] 是否中止该请求
 */
export function removePendingRequest(config, abort = false) {
  const key = getPendingKey(config);
  const controller = pendingMap.get(key);
  if (!controller) return;
  if (abort) controller.abort(`duplicate-request: ${key}`);
  pendingMap.delete(key);
}

/**
 * 登记请求并自动去重：同 key 的旧请求会被中止。
 * - 请求配置 noCancel === true 时跳过去重（如轮询、允许并发的场景）；
 * - 调用方已传入 signal 时不接管取消逻辑。
 * @param {import('axios').AxiosRequestConfig} config 请求配置
 */
export function addPendingRequest(config) {
  if (config.noCancel || config.signal) return;
  removePendingRequest(config, true);
  const controller = new AbortController();
  config.signal = controller.signal;
  pendingMap.set(getPendingKey(config), controller);
}

/** 中止全部 pending 请求（如退出登录、路由切换时调用） */
export function removeAllPendingRequest() {
  pendingMap.forEach((controller) => controller.abort('cancel-all'));
  pendingMap.clear();
}
