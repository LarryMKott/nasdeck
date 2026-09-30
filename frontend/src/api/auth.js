'use strict';

/** 认证域 API（全局共用） */
import { get, post } from '@/utils/request';

/**
 * 账号密码登录
 * @param {{username: string, password: string}} data 登录表单
 * @returns {Promise<{code: number, data: {accessToken: string, refreshToken: string}, message: string}>}
 */
export function apiLogin(data) {
  return post('/auth/login', data);
}

/**
 * 退出登录
 * @returns {Promise<{code: number, data: null, message: string}>}
 */
export function apiLogout() {
  return post('/auth/logout');
}

/**
 * 获取当前登录用户信息（含角色与权限标识）
 * @returns {Promise<{code: number, data: {userId: number, username: string, nickname: string, avatar: string, roles: string[], permissions: string[]}, message: string}>}
 */
export function apiGetUserInfo() {
  return get('/auth/user/info');
}
