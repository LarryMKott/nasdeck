'use strict';

/** 全局自定义指令注册入口 */
import { permission } from './permission';

export default {
  /**
   * Vue 插件安装入口
   * @param {import('vue').App} app Vue 应用实例
   */
  install(app) {
    app.directive('permission', permission);
  },
};
