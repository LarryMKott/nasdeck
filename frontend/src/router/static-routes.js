'use strict';

/**
 * 静态路由：无需权限即可访问的页面。
 * 注意：404 兜底路由（NOT_FOUND_ROUTE）不在此注册，
 * 而是在动态路由注入完成后追加，避免刷新时深链接被提前拦截。
 */
import Layout from '@/layouts/index.vue';

/** 主布局路由（菜单与动态业务路由均挂载在它下面） */
export const LAYOUT_ROUTE = {
  path: '/',
  name: 'Layout',
  component: Layout,
  redirect: '/nasdeck/dash',
  meta: { title: '首页', hidden: true },
  children: [],
};

/** 登录页 */
export const LOGIN_ROUTE = {
  path: '/login',
  name: 'Login',
  component: () => import('@/views/login/LoginView.vue'),
  meta: { title: '登录', hidden: true },
};

/** 无权限提示页 */
export const FORBIDDEN_ROUTE = {
  path: '/401',
  name: 'Forbidden',
  component: () => import('@/views/error/ForbiddenView.vue'),
  meta: { title: '无权访问', hidden: true },
};

/** 404 兜底路由（动态注入完成后由守卫追加） */
export const NOT_FOUND_ROUTE = {
  path: '/:pathMatch(.*)*',
  name: 'NotFound',
  component: () => import('@/views/error/NotFoundView.vue'),
  meta: { title: '页面不存在', hidden: true },
};

/** @type {import('vue-router').RouteRecordRaw[]} createRouter 初始路由表 */
export const staticRoutes = [LAYOUT_ROUTE, LOGIN_ROUTE, FORBIDDEN_ROUTE];
