'use strict';

/**
 * nasdeck 后端数据层统一入口（契约 §7）：
 * - fetch + credentials include + cache no-store + AbortController 超时
 * - 信封解包：code===0 返回 data，否则抛 ApiError；非信封响应（FastAPI detail）也归一
 * - 基址：fnOS 网关形态从 pathname 截 index.cgi 前缀，直连形态为空串
 */

export class ApiError extends Error {
  constructor(message, status = 0, payload = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status; // 0 表示网络层失败（后端不可达）
    this.code = payload?.code ?? 0;
    this.payload = payload;
  }
}

// 统一网关形态转发前缀（ui/config 的 gatewayPrefix，与 cmd/main 导出的
// NASDECK_GATEWAY_PREFIX 同源；JS 内联常量避免构建期依赖）
const GATEWAY_PREFIX = '/app/com.dashboard.nasdeck';

/** 计算基址：CGI 反代形态截 index.cgi 前缀，统一网关形态取网关前缀，直连为空串 */
export function apiBase() {
  if (typeof location === 'undefined') return '';
  const pathname = location.pathname;
  const marker = 'index.cgi';
  const idx = pathname.indexOf(marker);
  if (idx >= 0) return pathname.slice(0, idx + marker.length);
  if (pathname === GATEWAY_PREFIX || pathname.startsWith(`${GATEWAY_PREFIX}/`)) {
    return GATEWAY_PREFIX;
  }
  return '';
}

/**
 * 请求并解信封
 * @param {string} path 以 /api/v1 开头的接口路径
 * @param {{method?: string, body?: object, timeout?: number}} [opts]
 * @returns {Promise<any>} 信封 data 字段
 */
export async function apiData(path, opts = {}) {
  const { method = 'GET', body, timeout = 30000 } = opts;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const resp = await fetch(apiBase() + path, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: 'include',
      cache: 'no-store',
      signal: ctrl.signal,
    });
    const json = await resp.json().catch(() => null);
    if (!json || typeof json.code !== 'number') {
      // 网关 404 包 200 / FastAPI {detail} 等，都按业务失败归一（契约 §7.1）
      throw new ApiError(json?.detail ?? `HTTP ${resp.status}`, resp.status, json);
    }
    if (json.code !== 0) throw new ApiError(json.message ?? `code ${json.code}`, resp.status, json);
    return json.data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(error.name === 'AbortError' ? '请求超时' : '后端不可达', 0, null);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * apiData 的容错变体：失败返回 null 而非抛错。
 * 多源并发取数时「个别源缺失保持骨架空值」的统一收口（适配层专用）。
 * @template T
 * @param {string} path
 * @param {{method?: string, body?: object, timeout?: number}} [opts]
 * @returns {Promise<T|null>}
 */
export async function safe(path, opts) {
  try {
    return /** @type {T} */ (await apiData(path, opts));
  } catch {
    return null;
  }
}
