'use strict';

/**
 * i18n 翻译入口（经 vite AutoImport dirs 全局可用，SFC 内直接写 t('…')）。
 * 中文原文即字典 key：zh-CN 下原样返回（支持 {name} 插值），其他语言查 en-US
 * 字典、未命中回退中文原文——增量迁移时未包裹/未翻译的文案自然保持中文。
 */

import { locale, dictFor } from './locale';

function interpolate(text, vars) {
  if (!vars) return text;
  return String(text).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? vars[k] : m));
}

export function t(text, vars) {
  if (!text) return text;
  if (locale.value === 'zh-CN') return interpolate(text, vars);
  const hit = dictFor(locale.value)?.[text];
  return interpolate(hit !== undefined ? hit : text, vars);
}
