'use strict';

/**
 * axios 实例与快捷方法。
 *
 * 响应约定：业务接口统一返回后端响应结构 { code, data, message }；
 * Blob / 非标准结构返回完整 AxiosResponse（见 download）。
 */
import axios from 'axios';
import { REQUEST_TIMEOUT } from './config';
import { setupRequestInterceptor, setupResponseInterceptor } from './interceptors';
import { setupMock } from '@/mock';

const service = axios.create({
  baseURL: import.meta.env.VITE_APP_BASE_API || '/',
  timeout: REQUEST_TIMEOUT,
});

// Mock 开关（VITE_USE_MOCK=true 时以自定义 adapter 拦截请求）
setupMock(service);

setupRequestInterceptor(service);
setupResponseInterceptor(service);

export default service;

/**
 * GET 请求
 * @param {string} url 请求地址
 * @param {object} [params] 查询参数
 * @param {import('axios').AxiosRequestConfig} [config] 额外配置
 * @returns {Promise<{code: number, data: *, message: string}>}
 */
export function get(url, params = undefined, config = {}) {
  return service.get(url, { params, ...config });
}

/**
 * POST 请求
 * @param {string} url 请求地址
 * @param {*} [data] 请求体
 * @param {import('axios').AxiosRequestConfig} [config] 额外配置
 * @returns {Promise<{code: number, data: *, message: string}>}
 */
export function post(url, data = undefined, config = {}) {
  return service.post(url, data, config);
}

/**
 * PUT 请求
 * @param {string} url 请求地址
 * @param {*} [data] 请求体
 * @param {import('axios').AxiosRequestConfig} [config] 额外配置
 * @returns {Promise<{code: number, data: *, message: string}>}
 */
export function put(url, data = undefined, config = {}) {
  return service.put(url, data, config);
}

/**
 * DELETE 请求
 * @param {string} url 请求地址
 * @param {object} [params] 查询参数
 * @param {import('axios').AxiosRequestConfig} [config] 额外配置
 * @returns {Promise<{code: number, data: *, message: string}>}
 */
export function del(url, params = undefined, config = {}) {
  return service.delete(url, { params, ...config });
}

/**
 * 下载文件（Blob 响应）
 * @param {string} url 请求地址
 * @param {object} [params] 查询参数
 * @param {import('axios').AxiosRequestConfig} [config] 额外配置
 * @param {string} [filename] 下载保存的文件名
 */
export async function download(url, params = {}, config = {}, filename = '下载文件') {
  const response = await service.get(url, { params, ...config, responseType: 'blob' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([response.data]));
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}
