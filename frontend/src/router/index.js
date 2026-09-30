'use strict';

/** 路由器实例：懒加载路由 + history 模式 + 全局守卫 */
import { createRouter, createWebHistory } from 'vue-router';
import { staticRoutes } from './static-routes';
import { setupGuard } from './guards';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: staticRoutes,
  strict: false,
  scrollBehavior: () => ({ top: 0 }),
});

setupGuard(router);

/**
 * 安装路由器（须在 setupStore 之后调用，守卫内部依赖 Pinia）
 * @param {import('vue').App} app Vue 应用实例
 */
export function setupRouter(app) {
  app.use(router);
}

export default router;
