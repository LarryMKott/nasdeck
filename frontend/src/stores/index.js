'use strict';

/** Pinia 装配入口：按领域拆分 store，统一注册状态持久化插件 */
import { createPinia } from 'pinia';
import { createPersistedState } from 'pinia-plugin-persistedstate';

/**
 * 安装 Pinia（含持久化插件，须先于 setupRouter 调用）
 * @param {import('vue').App} app Vue 应用实例
 */
export function setupStore(app) {
  const pinia = createPinia();
  pinia.use(createPersistedState());
  app.use(pinia);
}

export { useAppStore } from './modules/app';
export { useUserStore } from './modules/user';
export { usePermissionStore } from './modules/permission';
