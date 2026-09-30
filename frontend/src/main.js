'use strict';

/**
 * 应用入口。
 * 说明：ESM 模块天然运行在严格模式下（等同 'use strict'），
 * 业务代码中的 Vue/Router/Pinia API 由 unplugin-auto-import 自动导入，
 * 入口文件保持显式导入以便阅读完整装配流程。
 */
import { createApp } from 'vue';
import App from './App.vue';
import { setupStore } from './stores';
import { setupRouter } from './router';
import directives from './directives';
import 'element-plus/theme-chalk/dark/css-vars.css';
import '@/styles/index.scss';

const app = createApp(App);

// 顺序要求：Pinia 先于 Router 安装（路由守卫内使用 store）
setupStore(app);
setupRouter(app);
app.use(directives);

// 全局运行时异常兜底
app.config.errorHandler = (error, _instance, info) => {
  console.error('[全局异常]', error, info);
};

app.mount('#app');
