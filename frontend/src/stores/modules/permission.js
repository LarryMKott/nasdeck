'use strict';

/**
 * 权限域状态：按角色/权限过滤动态路由并注入。
 * 路由权限规则：meta.roles 优先，其次 meta.permissions，均未配置默认放行。
 */
import { defineStore } from 'pinia';
import { dynamicRoutes } from '@/router/dynamic-routes';
import { STORAGE_PREFIX } from '@/constants';

/**
 * 判断路由是否对当前用户可见
 * @param {import('vue-router').RouteMeta} [meta] 路由元信息
 * @param {string[]} roles 角色编码列表
 * @param {string[]} permissions 权限标识列表
 * @returns {boolean}
 */
function hasRoutePermission(meta = {}, roles, permissions) {
  if (Array.isArray(meta.roles) && meta.roles.length) {
    return meta.roles.some((role) => roles.includes(role));
  }
  if (Array.isArray(meta.permissions) && meta.permissions.length) {
    return meta.permissions.some((permission) => permissions.includes(permission));
  }
  return true;
}

/**
 * 递归过滤动态路由，仅保留当前用户可访问的分支
 * @param {import('vue-router').RouteRecordRaw[]} routes 待过滤路由
 * @param {string[]} roles 角色编码列表
 * @param {string[]} permissions 权限标识列表
 * @returns {import('vue-router').RouteRecordRaw[]}
 */
function filterAsyncRoutes(routes, roles, permissions) {
  const result = [];
  routes.forEach((route) => {
    if (!hasRoutePermission(route.meta, roles, permissions)) return;
    const copy = { ...route };
    if (Array.isArray(copy.children) && copy.children.length) {
      copy.children = filterAsyncRoutes(copy.children, roles, permissions);
      if (!copy.children.length) return;
    }
    result.push(copy);
  });
  return result;
}

export const usePermissionStore = defineStore('permission', {
  state: () => ({
    /** 动态路由是否已生成（内存态，刷新后由守卫重新生成） */
    isGenerated: false,
    /** 当前用户可访问的动态路由 */
    accessRoutes: [],
  }),

  getters: {
    /** 侧边栏菜单：过滤 hidden 顶级路由与子路由 */
    menuRoutes(state) {
      return state.accessRoutes
        .filter((route) => !route.meta?.hidden)
        .map((route) => ({
          ...route,
          children: (route.children ?? []).filter((child) => !child.meta?.hidden),
        }));
    },

    /** keep-alive 缓存名单（要求组件 name 与路由 name 一致） */
    cachedViews(state) {
      const names = [];
      const walk = (routes) => {
        routes.forEach((route) => {
          if (route.meta?.keepAlive && route.name) names.push(route.name);
          if (route.children?.length) walk(route.children);
        });
      };
      walk(state.accessRoutes);
      return names;
    },
  },

  actions: {
    /**
     * 根据角色/权限生成动态路由（重复调用直接返回缓存结果）
     * @param {string[]} [roles] 角色编码列表
     * @param {string[]} [permissions] 权限标识列表
     * @returns {import('vue-router').RouteRecordRaw[]} 可访问路由（含 404 兜底）
     */
    generateRoutes(roles = [], permissions = []) {
      if (this.isGenerated) return this.accessRoutes;
      this.accessRoutes = filterAsyncRoutes(dynamicRoutes, roles, permissions);
      this.isGenerated = true;
      return this.accessRoutes;
    },

    /** 重置权限路由（退出登录时调用） */
    reset() {
      this.isGenerated = false;
      this.accessRoutes = [];
    },
  },

  persist: {
    key: `${STORAGE_PREFIX}permission`,
    storage: sessionStorage,
    paths: [],
  },
});
