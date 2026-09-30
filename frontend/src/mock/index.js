'use strict';

/**
 * 本地 Mock：以自定义 axios adapter 拦截请求并返回 mockRoutes 中的数据，
 * 与真实后端完全解耦——关闭 VITE_USE_MOCK 即恢复原生网络请求，零代码改动。
 */
import { mockRoutes } from './handlers';

/** @returns {boolean} Mock 是否启用 */
export function isMockEnabled() {
  return String(import.meta.env.VITE_USE_MOCK ?? 'false').toLowerCase() === 'true';
}

/** @param {string} url 从 URL 中解析查询参数对象 */
function parseQuery(url) {
  const index = url.indexOf('?');
  return Object.fromEntries(new URLSearchParams(index >= 0 ? url.slice(index + 1) : ''));
}

/**
 * 匹配 mock 路由
 * @param {string} method 请求方法
 * @param {string} path 请求路径（不含 baseURL）
 */
function matchRoute(method, path) {
  return mockRoutes.find((route) => {
    if (route.method !== method) return false;
    return route.path instanceof RegExp ? route.path.test(path) : route.path === path;
  });
}

/** @param {*} text 安全 JSON 解析，失败返回 null */
function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * 组装 mock 响应数据
 * @param {import('axios').AxiosRequestConfig} config axios 请求配置
 * @returns {{code: number, message: string, data: *}}
 */
function buildResult(config) {
  let url = config.url ?? '';
  const baseURL = config.baseURL ?? '';
  if (baseURL && url.startsWith(baseURL)) url = url.slice(baseURL.length);

  const method = String(config.method ?? 'get').toLowerCase();
  const route = matchRoute(method, url);
  if (!route) {
    return { code: 404, message: `Mock 未实现接口：${method.toUpperCase()} ${url}`, data: null };
  }

  return route.handler({
    query: parseQuery(url),
    body: safeJsonParse(config.data),
    headers: config.headers,
    match: route.path instanceof RegExp ? url.match(route.path) : [],
  });
}

/** 创建 axios mock 适配器（模拟 120-400ms 网络延迟） */
function createMockAdapter() {
  return (config) =>
    new Promise((resolve) => {
      const latency = 120 + Math.floor(Math.random() * 280);
      setTimeout(() => {
        resolve({
          data: buildResult(config),
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
          request: { mock: true },
        });
      }, latency);
    });
}

/**
 * 按环境变量启用本地 Mock
 * @param {import('axios').AxiosInstance} service 业务 axios 实例
 */
export function setupMock(service) {
  if (!isMockEnabled()) return;
  service.defaults.adapter = createMockAdapter();
  // eslint-disable-next-line no-console -- 有意的启动提示，生产构建时会被移除
  console.info('[mock] 已启用本地 Mock 数据（.env 中 VITE_USE_MOCK 可关闭）');
}
