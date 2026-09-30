'use strict';

/** 全局常量定义 */

/** 本地存储 key 前缀（含 pinia 持久化、token 缓存等） */
export const STORAGE_PREFIX = import.meta.env.VITE_STORAGE_PREFIX || 'vue_admin_';

/** 路由守卫白名单：无需登录即可访问的页面路径 */
export const WHITE_LIST = ['/login'];
