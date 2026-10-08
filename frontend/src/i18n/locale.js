'use strict';

/**
 * 语言域状态与解析（中文原文作 key 的字典 i18n，零依赖）。
 * 优先级：nd_locale 强制覆盖 > 飞牛桌面语言（micro_app SDK 桥）> 浏览器语言 > zh-CN。
 */

import { ref } from 'vue';
import enUS from './en-US';

const DICTS = { 'en-US': enUS };
const STORAGE_KEY = 'nd_locale'; // 'auto'（默认，跟随宿主/浏览器）| 'zh-CN' | 'en-US'

/** 当前生效语言（reactive：切换即全 UI 联动） */
export const locale = ref('zh-CN');

function normalize(lang) {
  const l = String(lang || '').toLowerCase();
  if (l.startsWith('en')) return 'en-US';
  if (l.startsWith('zh')) return 'zh-CN';
  return null;
}

function apply(lang) {
  const next = normalize(lang);
  if (next) locale.value = next;
}

function hasOverride() {
  const v = localStorage.getItem(STORAGE_KEY);
  return !!v && v !== 'auto';
}

/** 解析生效语言：强制覆盖 > 宿主语言（上次桥上报的）> 浏览器语言 */
function resolve() {
  const override = localStorage.getItem(STORAGE_KEY);
  if (override && override !== 'auto') {
    apply(override);
    return;
  }
  apply(navigator.language);
}

/** 宿主（飞牛桌面）语言上报——无强制覆盖时生效；轮询/事件均走此入口 */
export function setHostLanguage(lang) {
  if (hasOverride()) return;
  apply(lang);
}

/** 手动强制语言（'auto' 恢复跟随）；预留 UI 入口，暂供调试 */
export function setLocale(v) {
  localStorage.setItem(STORAGE_KEY, normalize(v) || 'auto');
  resolve();
}

/** 当前语言下的字典（供 t() 与需要整段文案的调用方） */
export function dictFor(lang) {
  return DICTS[normalize(lang) || locale.value] ?? null;
}

resolve();
