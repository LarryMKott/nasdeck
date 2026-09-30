'use strict';

/** @type {import('stylelint').Config} */
module.exports = {
  extends: [
    'stylelint-config-standard-scss',
    'stylelint-config-recommended-vue',
    'stylelint-config-recess-order',
  ],
  rules: {
    // 需要覆盖 Element Plus 类名（.el-*），不做类名命名格式约束
    'selector-class-pattern': null,
    // 覆盖第三方组件样式时难以保证选择器特异性顺序
    'no-descending-specificity': null,
    // .vue 样式块经 postcss-html 解析，无 SCSS 语义：
    // 原生 at-rule/value 校验会误报 @include 与 SCSS 变量，交由 scss 规则集处理
    'at-rule-no-unknown': null,
    'declaration-property-value-no-unknown': null,
    'import-notation': 'string',
  },
  ignoreFiles: ['dist/**', 'node_modules/**', 'coverage/**'],
};
