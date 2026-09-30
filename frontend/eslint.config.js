'use strict';

import { readFileSync } from 'node:fs';

import js from '@eslint/js';
import eslintConfigPrettier from 'eslint-config-prettier';
import pluginVue from 'eslint-plugin-vue';
import globals from 'globals';

/** 读取 unplugin-auto-import 生成的全局变量清单（首次构建前文件可能不存在） */
function loadAutoImportGlobals() {
  try {
    const content = readFileSync(new URL('./.eslintrc-auto-import.json', import.meta.url), 'utf-8');
    return JSON.parse(content).globals ?? {};
  } catch {
    return {};
  }
}

export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**', '*.local'],
  },

  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  // 关闭所有与 Prettier 冲突的格式类规则（必须放在最后）
  eslintConfigPrettier,

  {
    // Node 环境下的构建配置与工程脚本
    files: ['vite.config.js', 'eslint.config.js', '**/*.cjs'],
    languageOptions: {
      globals: { ...globals.node },
    },
  },

  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...loadAutoImportGlobals(),
        // Element Plus 消息类 API 通过 unplugin-auto-import 注入，显式声明兜底
        ElMessage: 'readonly',
        ElMessageBox: 'readonly',
        ElNotification: 'readonly',
        ElLoading: 'readonly',
      },
    },
    rules: {
      // ---- 严格校验 ----
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'warn',
      'no-var': 'error',
      'prefer-const': 'error',
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'prefer-template': 'error',
      'object-shorthand': ['error', 'always'],
      'no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' },
      ],
      'no-param-reassign': ['error', { props: false }],
      camelcase: ['error', { properties: 'never' }],
      curly: ['error', 'multi-line'],
      'prefer-promise-reject-errors': ['error', { allowEmptyReject: true }],

      // ---- Vue ----
      'vue/multi-word-component-names': ['error', { ignores: ['App'] }],
      'vue/component-name-in-template-casing': ['error', 'kebab-case'],
      // 纯 JS 项目中可选 prop 不强制书写 default
      'vue/require-default-prop': 'off',
    },
  },
];
