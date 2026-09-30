'use strict';

/**
 * 登录令牌读写：token 本体通过 utils/cache 持久化，
 * 不进入 Pinia 持久化，避免与 store 状态双向同步产生歧义。
 */
import { getCache, setCache, removeCache } from './cache';

export const ACCESS_TOKEN_KEY = 'access_token';
export const REFRESH_TOKEN_KEY = 'refresh_token';

const TOKEN_EXPIRE = 7 * 24 * 60 * 60 * 1000;

/** @returns {string | null} 访问令牌 */
export function getAccessToken() {
  return getCache(ACCESS_TOKEN_KEY);
}

/** @returns {string | null} 刷新令牌 */
export function getRefreshToken() {
  return getCache(REFRESH_TOKEN_KEY);
}

/**
 * 同时写入访问令牌与刷新令牌
 * @param {{ accessToken: string, refreshToken?: string }} tokens 令牌对
 */
export function setToken({ accessToken, refreshToken }) {
  if (accessToken) setCache(ACCESS_TOKEN_KEY, accessToken, { expire: TOKEN_EXPIRE });
  if (refreshToken) setCache(REFRESH_TOKEN_KEY, refreshToken, { expire: TOKEN_EXPIRE });
}

/** 清除全部令牌（退出登录 / 刷新失败时调用） */
export function clearToken() {
  removeCache(ACCESS_TOKEN_KEY);
  removeCache(REFRESH_TOKEN_KEY);
}
