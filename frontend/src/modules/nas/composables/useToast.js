'use strict';

/**
 * 全局轻量 toast（原型 D2）：写操作成功/失败、临界全速提示、渠道测试结果。
 * 任一模块 `toast('ok'|'bad'|'warn'|'info', '文案')`；最多堆叠 3 条，3.5s 自动消失。
 */
import { reactive } from 'vue';

const toasts = reactive([]);
let uid = 0;

export function toast(kind, message) {
  const id = ++uid;
  toasts.push({ id, kind, message });
  while (toasts.length > 3) toasts.shift();
  setTimeout(() => {
    const i = toasts.findIndex((t) => t.id === id);
    if (i >= 0) toasts.splice(i, 1);
  }, 3500);
}

export function useToasts() {
  return toasts;
}
