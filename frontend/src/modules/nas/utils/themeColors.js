'use strict';

/**
 * 主题联动图表色板：从 .nd 根元素的 --ch-* CSS 变量读取（unraid.scss 各皮肤
 * 自带色板），ref 响应式——主题切换后 refresh 一次，所有 canvas/图表随动。
 * 默认值为黑主题 UNRAID 板（.nd 未挂载/SSR 兜底）。
 */

import { ref } from 'vue';

const DEFAULTS = {
  acc: '#f15a2c',
  ok: '#3fb68b',
  info: '#5b9cf6',
  purp: '#a077e8',
  warn: '#eca43c',
  temp: '#e8734b',
  gpu: '#c291f0',
};

export const chartColors = ref({ ...DEFAULTS });

/** 读取当前生效皮肤 --ch-* 变量刷新色板（主题切换 / 应用挂载后调用） */
export function refreshChartColors() {
  const nd = document.querySelector('.nd');
  if (!nd) return;
  const cs = getComputedStyle(nd);
  const read = (name, fallback) => cs.getPropertyValue(name).trim() || fallback;
  chartColors.value = {
    acc: read('--ch-acc', DEFAULTS.acc),
    ok: read('--ch-ok', DEFAULTS.ok),
    info: read('--ch-info', DEFAULTS.info),
    purp: read('--ch-purp', DEFAULTS.purp),
    warn: read('--ch-warn', DEFAULTS.warn),
    temp: read('--ch-temp', DEFAULTS.temp),
    gpu: read('--ch-gpu', DEFAULTS.gpu),
  };
}
