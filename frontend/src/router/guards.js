'use strict';

/**
 * 全局路由守卫：动态路由注入。
 * 面板鉴权由飞牛登录态承担（index.cgi 反代前已校验），应用内不做登录拦截；
 * 守卫只负责首次导航（含刷新后）注入本地会话并生成动态路由，再重放当前导航。
 */
import NProgress from 'nprogress';
import 'nprogress/nprogress.css';
import { useUserStore } from '@/stores/modules/user';
import { usePermissionStore } from '@/stores/modules/permission';
import { defaultSettings } from '@/config/settings';

/**
 * 注册全局前置/后置守卫
 * @param {import('vue-router').Router} router 路由实例
 */
export function setupGuard(router) {
  router.beforeEach((to) => {
    NProgress.start();
    document.title = to.meta?.title
      ? `${to.meta.title} - ${defaultSettings.title}`
      : defaultSettings.title;

    const userStore = useUserStore();
    const permissionStore = usePermissionStore();

    // 首次导航：注入本地会话 → 生成动态路由 → 重放当前导航使新路由立即生效
    if (!permissionStore.isGenerated) {
      userStore.ensureSession();
      const accessRoutes = permissionStore.generateRoutes(userStore.roles, userStore.permissions);
      accessRoutes.forEach((route) => router.addRoute(route));
      return { ...to, replace: true };
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
