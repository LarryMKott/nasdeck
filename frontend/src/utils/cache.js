'use strict';

/**
 * 浏览器缓存封装：统一 localStorage / sessionStorage 访问，
 * 支持 JSON 序列化与毫秒级过期时间，所有 key 自动附加全局前缀。
 */
import { STORAGE_PREFIX } from '@/constants';

const DEFAULT_TYPE = 'local';

/** @param {string} [type] 缓存类型：local | session */
function getStorage(type = DEFAULT_TYPE) {
  return type === 'session' ? window.sessionStorage : window.localStorage;
}

/**
 * 写入缓存
 * @param {string} key 缓存键（自动附加前缀）
 * @param {*} value 任意可序列化值
 * @param {{ type?: string, expire?: number }} [options] type: local|session；expire: 有效期（毫秒）
 */
export function setCache(key, value, { type = DEFAULT_TYPE, expire } = {}) {
  const payload = { value, expire: expire ? Date.now() + expire : null };
  try {
    getStorage(type).setItem(STORAGE_PREFIX + key, JSON.stringify(payload));
  } catch (error) {
    console.warn('[cache] 写入缓存失败：', error);
  }
}

/**
 * 读取缓存，过期或不存在返回 null
 * @param {string} key 缓存键（自动附加前缀）
 * @param {{ type?: string }} [options] type: local|session
 * @returns {*}
 */
export function getCache(key, { type = DEFAULT_TYPE } = {}) {
  try {
    const raw = getStorage(type).getItem(STORAGE_PREFIX + key);
    if (!raw) return null;
    const payload = JSON.parse(raw);
    if (payload.expire && Date.now() > payload.expire) {
      removeCache(key, { type });
      return null;
    }
    return payload.value;
  } catch (error) {
    console.warn('[cache] 读取缓存失败：', error);
    return null;
  }
}

/**
 * 移除缓存
 * @param {string} key 缓存键（自动附加前缀）
 * @param {{ type?: string }} [options] type: local|session
 */
export function removeCache(key, { type = DEFAULT_TYPE } = {}) {
  try {
    getStorage(type).removeItem(STORAGE_PREFIX + key);
  } catch (error) {
    console.warn('[cache] 移除缓存失败：', error);
  }
}
