'use strict';

/** 系统管理模块 API */
import { get, post, put, del } from '@/utils/request';

/**
 * 分页查询用户
 * @param {{page: number, pageSize: number, keyword?: string, status?: number | ''}} params 查询参数
 * @returns {Promise<{code: number, data: {list: Array, total: number, page: number, pageSize: number}, message: string}>}
 */
export function getUserPage(params) {
  return get('/system/user/page', params);
}

/**
 * 创建用户
 * @param {object} data 用户表单数据
 * @returns {Promise<{code: number, data: object, message: string}>}
 */
export function createUser(data) {
  return post('/system/user', data);
}

/**
 * 更新用户
 * @param {number} id 用户 ID
 * @param {object} data 用户表单数据
 * @returns {Promise<{code: number, data: object, message: string}>}
 */
export function updateUser(id, data) {
  return put(`/system/user/${id}`, data);
}

/**
 * 删除用户
 * @param {number} id 用户 ID
 * @returns {Promise<{code: number, data: null, message: string}>}
 */
export function deleteUser(id) {
  return del(`/system/user/${id}`);
}

/**
 * 获取角色列表
 * @returns {Promise<{code: number, data: Array, message: string}>}
 */
export function getRoleList() {
  return get('/system/role/list');
}
