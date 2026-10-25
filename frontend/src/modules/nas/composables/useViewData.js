'use strict';

/**
 * 视图数据组合器：视图传入 (适配器, mock 初始值)，
 * 得到响应式 data（形状与 mock 一致，模板零改动）+ live 标记 + 手动刷新。
 * onMounted 与 keep-alive onActivated 时都会拉取；后端不可达时静默保持演示值。
 *
 * 竞态守卫（评审 2026-10-25 F-N1）：refresh 带单调序号，慢响应晚归时丢弃
 * （轮询/快速切页下旧数据不再覆盖新数据）；refreshing 供页头真实转圈。
 */
import { onActivated, onMounted, ref } from 'vue';
import { demoMode } from './useDemoMode';

export function useViewData(loader, initial, { immediate = true } = {}) {
  const data = ref(initial);
  const live = ref(false);
  const extra = ref(null); // 适配器可附带的元信息（如 docker 不可用原因）
  const lastUpdated = ref('—'); // 最近一次成功取数时刻（页头「最后更新」）
  const refreshing = ref(false);
  let seq = 0;

  async function refresh() {
    const my = ++seq;
    refreshing.value = true;
    try {
      const result = await loader();
      if (my !== seq) return; // 已有更新一轮：丢弃过期响应
      if (result?.data) {
        data.value = result.data;
        live.value = !!result.live;
        demoMode.value = live.value ? false : demoMode.value || !result.live;
        if (result.live) demoMode.value = false;
        extra.value = result.extra ?? null;
        const now = new Date();
        const pad = (x) => String(x).padStart(2, '0');
        lastUpdated.value = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
      }
    } catch {
      /* 保持演示值 */
    } finally {
      if (my === seq) refreshing.value = false;
    }
  }

  if (immediate) {
    // keep-alive 下首挂载 onMounted 与 onActivated 都会触发：跳过首次激活，
    // 否则每次进页请求翻倍（DashView 一次进页曾发 16 个请求）
    let activated = false;
    onMounted(refresh);
    onActivated(() => {
      if (activated) refresh();
      activated = true;
    });
  }
  return { data, live, extra, refresh, refreshing, lastUpdated };
}
