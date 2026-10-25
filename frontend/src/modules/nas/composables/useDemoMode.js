'use strict';

/**
 * 演示模式全局状态（原型 D4）：任一视图的适配器回退演示数据时亮横幅，
 * 「本次会话不再提示」记忆在 sessionStorage。此前演示数据只在页头 tag 里
 * 出现一个小徽标，用户容易把假数字当真机状态。
 */
import { ref } from 'vue';

export const demoMode = ref(false);
export const demoDismissed = ref(sessionStorage.getItem('nd_demo_dismissed') === '1');

export function dismissDemo() {
  demoDismissed.value = true;
  try {
    sessionStorage.setItem('nd_demo_dismissed', '1');
  } catch {
    /* 隐私模式等场景静默 */
  }
}
