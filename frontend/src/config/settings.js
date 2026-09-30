'use strict';

/** 应用默认配置（与环境相关的配置请放 .env* 文件） */
export const defaultSettings = {
  /** 应用标题（与 VITE_APP_TITLE 保持一致） */
  title: import.meta.env.VITE_APP_TITLE || 'Vue Admin',
  /** 是否显示面包屑 */
  showBreadcrumb: true,
};
