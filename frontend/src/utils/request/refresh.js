'use strict';

/**
 * 无感刷新令牌：401 时用 refreshToken 换取新 accessToken 并重放原请求。
 * 并发 401 只触发一次刷新，其余请求进入等待队列，刷新完成后统一重放。
 */
import axios from 'axios';
import { getRefreshToken, setToken, clearToken } from '@/utils/auth';
import { REFRESH_TOKEN_URL, SUCCESS_CODE, REQUEST_TIMEOUT } from './config';

/** 是否正在刷新令牌 */
let refreshing = false;

/** @type {Array<(token: string | null) => void>} 等待重放的请求回调队列 */
let waitingQueue = [];

/** @returns {boolean} 是否正在刷新令牌 */
export function isRefreshingToken() {
  return refreshing;
}

/**
 * 使用刷新令牌换取新的令牌对（独立 axios 实例，不经过业务拦截器）
 * @returns {Promise<string>} 新的访问令牌
 * @throws {Error} 刷新令牌缺失或后端拒绝时抛错
 */
export async function refreshAccessToken() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) throw new Error('缺少刷新令牌');

  const instance = axios.create({
    baseURL: import.meta.env.VITE_APP_BASE_API || '/',
    timeout: REQUEST_TIMEOUT,
  });
  const { data } = await instance.post(
    REFRESH_TOKEN_URL,
    { refreshToken },
    { headers: { Authorization: `Bearer ${refreshToken}` } }
  );

  if (data?.code !== SUCCESS_CODE) throw new Error(data?.message || '刷新令牌已失效');
  setToken(data.data);
  return data.data.accessToken;
}

/**
 * 统一处理 401：首个请求触发刷新并重放，后续请求排队等待
 * @param {import('axios').AxiosInstance} service 业务 axios 实例
 * @param {import('axios').AxiosRequestConfig} config 原始请求配置
 * @returns {Promise<import('axios').AxiosResponse>} 重放后的响应
 */
export function handleUnauthorized(service, config) {
  // 已在刷新中：当前请求入队，刷新完成后重放
  if (refreshing) {
    return new Promise((resolve, reject) => {
      waitingQueue.push((token) => {
        if (token) resolve(service(config));
        else reject(new Error('登录已失效'));
      });
    });
  }

  refreshing = true;
  return refreshAccessToken()
    .then((token) => {
      waitingQueue.forEach((callback) => callback(token));
      waitingQueue = [];
      return service(config);
    })
    .catch((error) => {
      // 刷新失败：清空令牌并回登录页（携带当前地址便于重新登录后回跳）
      waitingQueue.forEach((callback) => callback(null));
      waitingQueue = [];
      clearToken();
      const redirect = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/login?redirect=${redirect}`;
      throw error;
    })
    .finally(() => {
      refreshing = false;
    });
}
