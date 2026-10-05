'use strict';

/**
 * 视图适配层内部共享助手（无网络、无状态）。
 */

/** ISO 时间 → HH:MM（告警事件/日志时间列） */
export function hhmm(iso) {
  const t = new Date(iso);
  return isNaN(t)
    ? ''
    : `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`;
}

/** 多源并发取数的结果解包：个别源失败 → null（配合 Promise.allSettled） */
export function pick(settled) {
  return settled.status === 'fulfilled' ? settled.value : null;
}

/** 秒 → 「N 天 N 小时」（不足 1 天只显小时） */
export function uptimeText(seconds) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return days ? `${days} 天 ${hours} 小时` : `${hours} 小时`;
}
