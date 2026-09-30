'use strict';

import { fileURLToPath, URL } from 'node:url';

import AutoImport from 'unplugin-auto-import/vite';
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers';
import Components from 'unplugin-vue-components/vite';
import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import viteCompression from 'vite-plugin-compression';

/**
 * 构建配置：
 * - 通过 loadEnv 读取多环境变量（.env / .env.development / .env.test / .env.production）
 * - 第三方库手动分包 + Gzip 压缩 + 关闭 sourcemap + 生产移除 console
 * - SCSS 全局变量通过 additionalData 注入（variables.scss 仅允许存放变量/混入，不能输出 CSS）
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const port = Number(env.VITE_PORT) || 5173;
  const enableGzip = env.VITE_BUILD_GZIP === 'true';
  const proxyTarget = env.VITE_PROXY_TARGET;

  return {
    base: env.VITE_PUBLIC_PATH || '/',

    plugins: [
      vue(),
      // API 自动导入：Vue / Vue Router / Pinia 及 Element Plus 消息类 API
      AutoImport({
        imports: ['vue', 'vue-router', 'pinia'],
        resolvers: [ElementPlusResolver({ importStyle: 'sass' })],
        vueTemplate: true,
        dts: false,
        // 生成 .eslintrc-auto-import.json，供 ESLint 识别自动导入的全局 API
        eslintrc: { enabled: true },
      }),
      // 组件自动导入：src/components 全局通用组件 + Element Plus 组件（样式按需）
      Components({
        dirs: ['src/components'],
        extensions: ['vue'],
        include: [/\.vue$/, /\.vue\?vue/],
        resolvers: [ElementPlusResolver({ importStyle: 'sass' })],
        dts: false,
      }),
      enableGzip &&
        viteCompression({
          verbose: true,
          disable: false,
          threshold: 10240,
          algorithm: 'gzip',
          ext: '.gz',
          deleteOriginFile: false,
        }),
    ].filter(Boolean),

    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },

    css: {
      preprocessorOptions: {
        scss: {
          api: 'modern-compiler',
          additionalData: `@use "@/styles/variables.scss" as *;`,
        },
      },
    },

    server: {
      host: '0.0.0.0',
      port,
      open: false,
      proxy: proxyTarget
        ? {
            [env.VITE_APP_BASE_API]: {
              target: proxyTarget,
              changeOrigin: true,
              ws: true, // WebSocket /api/v1/ws/realtime 同走代理
              // nasdeck 后端本身挂 /api/v1，默认不剥前缀；旧脚手架 mock 后端需剥前缀时开 VITE_PROXY_STRIP=true
              rewrite:
                env.VITE_PROXY_STRIP === 'true'
                  ? (path) => path.replace(new RegExp(`^${env.VITE_APP_BASE_API}`), '')
                  : undefined,
            },
          }
        : undefined,
    },

    esbuild: {
      // 生产构建移除调试代码（保留 console.warn / console.error 便于线上排障）
      drop: ['debugger'],
      pure: [
        'console.log',
        'console.info',
        'console.debug',
        'console.table',
        'console.time',
        'console.timeEnd',
        'console.trace',
      ],
    },

    build: {
      target: 'es2022',
      sourcemap: false,
      chunkSizeWarningLimit: 2000,
      rollupOptions: {
        output: {
          entryFileNames: 'assets/js/[name]-[hash].js',
          chunkFileNames: 'assets/js/[name]-[hash].js',
          assetFileNames: 'assets/[ext]/[name]-[hash][extname]',
          manualChunks: {
            'vue-vendor': ['vue', 'vue-router', 'pinia', 'pinia-plugin-persistedstate'],
            'element-vendor': ['element-plus', '@element-plus/icons-vue'],
            'vendor-misc': ['axios', 'nprogress'],
          },
        },
      },
    },
  };
});
