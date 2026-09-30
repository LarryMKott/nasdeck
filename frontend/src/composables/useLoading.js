'use strict';

/** loading 状态组合式函数 */
import { ref } from 'vue';

/**
 * 创建可复用的 loading 状态
 * @param {boolean} [initial] 初始状态
 * @returns {{loading: import('vue').Ref<boolean>, setLoading: (value: boolean) => void, wrap: <T>(fn: () => Promise<T>) => Promise<T>}}
 */
export function useLoading(initial = false) {
  const loading = ref(initial);

  /**
   * 设置 loading 状态
   * @param {boolean} value 目标状态
   */
  function setLoading(value) {
    loading.value = Boolean(value);
  }

  /**
   * 包裹异步函数：执行期间自动维护 loading
   * @template T
   * @param {() => Promise<T>} fn 异步任务
   * @returns {Promise<T>}
   */
  async function wrap(fn) {
    setLoading(true);
    try {
      return await fn();
    } finally {
      setLoading(false);
    }
  }

  return { loading, setLoading, wrap };
}
