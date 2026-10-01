'use strict';

/**
 * 视图数据组合器：视图传入 (适配器, mock 初始值)，
 * 得到响应式 data（形状与 mock 一致，模板零改动）+ live 标记 + 手动刷新。
 * onMounted 与 keep-alive onActivated 时都会拉取；后端不可达时静默保持演示值。
 */
import { onActivated, onMounted, ref } from 'vue';

export function useViewData(loader, initial, { immediate = true } = {}) {
  const data = ref(initial);
  const live = ref(false);
  const extra = ref(null); // 适配器可附带的元信息（如 docker 不可用原因）
  const lastUpdated = ref('—'); // 最近一次成功取数时刻（页头「最后更新」）

  async function refresh() {
    try {
      const result = await loader();
      if (result?.data) {
        data.value = result.data;
        live.value = !!result.live;
        extra.value = result.extra ?? null;
        const now = new Date();
        const pad = (x) => String(x).padStart(2, '0');
        lastUpdated.value = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
      }
    } catch {
      /* 保持演示值 */
    }
  }

  if (immediate) {
    onMounted(refresh);
    onActivated(refresh);
  }
  return { data, live, extra, refresh, lastUpdated };
}
