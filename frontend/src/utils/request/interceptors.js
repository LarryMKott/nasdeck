'use strict';

/**
 * axios 拦截器装配：
 * - 请求拦截：附加 Bearer Token、登记并自动取消重复请求；
 * - 响应拦截：剥离标准响应结构、统一错误码提示、401 走无感刷新重放、
 *   被取消的重复请求静默处理。
 */
import axios from 'axios';
import { ElMessage } from 'element-plus';
import { getAccessToken } from '@/utils/auth';
import { addPendingRequest, removePendingRequest } from './cancel';
import { handleUnauthorized } from './refresh';
import { SUCCESS_CODE, UNAUTHORIZED_CODE, HTTP_STATUS_MESSAGES } from './config';

/** 请求拦截：附加 Token + 重复请求登记 */
function onRequest(config) {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  addPendingRequest(config);
  return config;
}

/**
 * 安装请求拦截器
 * @param {import('axios').AxiosInstance} service axios 实例
 */
export function setupRequestInterceptor(service) {
  service.interceptors.request.use(onRequest);
}

/**
 * 安装响应拦截器（需持有实例引用以便 401 重放）
 * @param {import('axios').AxiosInstance} service axios 实例
 */
export function setupResponseInterceptor(service) {
  service.interceptors.response.use(
    (response) => {
      removePendingRequest(response.config);

      const payload = response?.data;
      // 非标准响应结构（Blob / 文本等）直接透传完整 response
      if (!payload || typeof payload.code === 'undefined') return response;

      if (payload.code === SUCCESS_CODE) return payload;

      // 业务 401：与 HTTP 401 同样走无感刷新
      if (payload.code === UNAUTHORIZED_CODE) return handleUnauthorized(service, response.config);

      const error = new Error(payload.message || '请求失败');
      error.handled = true;
      error.code = payload.code;
      ElMessage.error(payload.message || '请求失败');
      return Promise.reject(error);
    },
    (rawError) => {
      const config = rawError?.config ?? {};
      removePendingRequest(config);

      // 重复请求被自动取消：仅记录日志，不打扰用户
      if (axios.isCancel(rawError)) {
        console.warn('[request] 重复请求已自动取消：', rawError?.message);
        const cancelled = new Error('请求已取消');
        cancelled.cancelled = true;
        return Promise.reject(cancelled);
      }

      const status = rawError?.response?.status;
      const bizCode = rawError?.response?.data?.code;

      // HTTP 401 或业务 401：无感刷新 + 重放
      if (status === 401 || bizCode === UNAUTHORIZED_CODE) {
        return handleUnauthorized(service, config);
      }

      let message =
        rawError?.response?.data?.message ||
        (status && HTTP_STATUS_MESSAGES[status]) ||
        rawError?.message ||
        '网络异常，请稍后重试';
      if (
        rawError?.code === 'ECONNABORTED' ||
        String(rawError?.message ?? '').includes('timeout')
      ) {
        message = '请求超时，请稍后重试';
      }
      if (!rawError?.response && !window.navigator.onLine) {
        message = '网络已断开，请检查网络连接';
      }

      if (!rawError?.handled) ElMessage.error(message);
      return Promise.reject(rawError);
    }
  );
}
