'use strict';

/**
 * 全局路由守卫：登录校验 + 动态路由注入。
 * 流程：白名单放行 → 无 Token 跳登录 → 有 Token 且未生成动态路由时
 * 拉取用户信息并注入路由 → 重放当前导航。
 */
import NProgress from 'nprogress';
import 'nprogress/nprogress.css';
import { useUserStore } from '@/stores/modules/user';
import { usePermissionStore } from '@/stores/modules/permission';
import { WHITE_LIST } from '@/constants';
import { getAccessToken } from '@/utils/auth';
import { defaultSettings } from '@/config/settings';

/**
 * 注册全局前置/后置守卫
 * @param {import('vue-router').Router} router 路由实例
 */
export function setupGuard(router) {
  router.beforeEach(async (to) => {
    NProgress.start();
    document.title = to.meta?.title
      ? `${to.meta.title} - ${defaultSettings.title}`
      : defaultSettings.title;

    const token = getAccessToken();

    // 1. 未登录：仅放行白名单页面
    if (!token) {
      if (WHITE_LIST.includes(to.path)) return true;
      return {
        path: '/login',
        query: to.fullPath === '/' ? {} : { redirect: encodeURIComponent(to.fullPath) },
      };
    }

    // 2. 已登录访问登录页 → 回首页
    if (to.path === '/login') return { path: '/' };

    const userStore = useUserStore();
    const permissionStore = usePermissionStore();

    // 3. 首次导航（含浏览器刷新后）：拉取用户信息并注入动态路由
    if (!permissionStore.isGenerated) {
      try {
        if (!userStore.roles.length) await userStore.fetchGetUserInfo();
        const accessRoutes = permissionStore.generateRoutes(userStore.roles, userStore.permissions);
        accessRoutes.forEach((route) => router.addRoute(route));
        // 重新进入当前导航，使新注入的路由立即生效
        return { ...to, replace: true };
      } catch (error) {
        console.error('[router] 动态路由生成失败：', error);
        await userStore.logout();
        return { path: '/login', query: { redirect: encodeURIComponent(to.fullPath) } };
      }
    }

    return true;
  });

  router.afterEach(() => {
    NProgress.done();
  });

  router.onError(() => {
    NProgress.done();
  });
}
