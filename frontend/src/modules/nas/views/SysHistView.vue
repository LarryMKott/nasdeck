<script setup>
/** 历史趋势：六维度 × 三区间回看 + dataZoom 框选缩放 + 区间统计与报告导出（本地 mock） */
import { computed, onActivated, reactive, ref, watch } from 'vue';
import { colors } from '../mock';
import { walk, timeLabels } from '../utils/series';
import * as nasData from '../api/data';
import UPageHeader from '../components/UPageHeader.vue';
import ULineChart from '../components/ULineChart.vue';
import UDropdown from '../components/UDropdown.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasSysHist' });

/** 维度配置（色板/基准/波动/上下限/单位）。单位与后端口径一致：net/disk 均为 KB/s */
const DIMS = {
  cpu: { label: 'CPU', color: colors.acc, base: 25, vol: 14, min: 2, max: 96, unit: '%' },
  mem: { label: '内存', color: colors.purp, base: 44, vol: 7, min: 30, max: 70, unit: '%' },
  temp: { label: '温度', color: '#E8734B', base: 42, vol: 5, min: 28, max: 74, unit: '°C' },
  net: { label: '网络', color: colors.ok, base: 9, vol: 8, min: 0, max: 60, unit: ' KB/s' },
  disk: {
    label: '磁盘 IO',
    color: colors.info,
    base: 55,
    vol: 34,
    min: 0,
    max: 180,
    unit: ' KB/s',
  },
  gpu: { label: 'GPU', color: '#C291F0', base: 18, vol: 11, min: 0, max: 90, unit: '%' },
};

/** 区间配置：点数 / 采样间隔（秒）/ 种子偏移 */
const RANGES = {
  '24h': { n: 144, step: 600, seed: 11 },
  '7d': { n: 168, step: 3600, seed: 22 },
  '30d': { n: 360, step: 7200, seed: 33 },
};

const activeDim = ref('cpu');
const activeRange = ref('7d');

/** 演示回退序列（后端不可达时保持页面完整） */
const histData = computed(() => {
  const c = DIMS[activeDim.value];
  const r = RANGES[activeRange.value];
  return walk(r.n, r.seed * 7 + activeDim.value.length * 131, c.base, c.vol, c.min, c.max);
});

const fallbackLabels = computed(() => {
  const r = RANGES[activeRange.value];
  return timeLabels(r.n, r.step, true);
});

/** 后端 /monitor/history 真实数据（维度 × 区间变化即刷新） */
const remote = ref(null); // { series, labels, stats }
const remoteLive = ref(false);

const remoteStats = ref(null);
const lastUpdated = ref('—');

async function loadRemote() {
  const result = await nasData.fetchHistorySeries(activeDim.value, activeRange.value);
  if (result.live && result.data) {
    remote.value = result.data;
    remoteLive.value = true;
  } else {
    remote.value = null;
    remoteLive.value = false;
  }
  remoteStats.value = await nasData.fetchHistoryStats(activeDim.value, activeRange.value);
  const now = new Date();
  const pad = (x) => String(x).padStart(2, '0');
  lastUpdated.value = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

function exportAs(fmt) {
  window.open(nasData.historyExportUrl(activeDim.value, activeRange.value, fmt), '_blank');
}
// 维度/区间变化即刷新；keep-alive 回页时经 onActivated 再刷新。
// watch immediate 覆盖首挂载，onActivated 跳过首次（否则首进页连发 3 次）
watch([activeDim, activeRange], loadRemote, { immediate: true });
let firstActivation = true;
onActivated(() => {
  if (firstActivation) {
    firstActivation = false;
    return;
  }
  loadRemote();
});

const histSeries = computed(() => [
  {
    name: DIMS[activeDim.value].label,
    color: DIMS[activeDim.value].color,
    data: remoteLive.value ? remote.value.series : histData.value,
  },
]);

const histLabels = computed(() => (remoteLive.value ? remote.value.labels : fallbackLabels.value));

const histStats = computed(() => {
  if (remoteLive.value && remoteStats.value) return remoteStats.value;
  if (remoteLive.value) return remote.value.stats;
  const c = DIMS[activeDim.value];
  const data = histData.value;
  const avg = data.reduce((a, b) => a + b, 0) / data.length;
  return {
    avg: `${avg.toFixed(1)}${c.unit}`,
    max: `${Math.max(...data).toFixed(1)}${c.unit}`,
    n: data.length,
  };
});

/** 报告导出下拉 */
const exportOpen = ref(false);
const fmtOpen = reactive({ md: false, html: false, csv: false });
</script>

<template>
  <section>
    <u-page-header title="历史趋势" sub="六维度历史数据回看 · 报告导出" :updated="lastUpdated">
      <template #right>
        <div class="seg">
          <button
            v-for="(cfg, key) in RANGES"
            :key="key"
            :class="{ on: activeRange === key }"
            @click="activeRange = key"
          >
            {{ key }}
          </button>
        </div>
        <u-dropdown v-model="exportOpen">
          <template #trigger>
            <button class="btn">
              <u-icon name="dl" />报告导出<svg class="ico" style="width: 11px; height: 11px">
                <use href="#nd-i-chevd" />
              </svg>
            </button>
          </template>
          <button @click="exportAs('markdown')"><u-icon name="dl" />Markdown 报告</button>
          <button @click="exportAs('html')"><u-icon name="dl" />HTML 报告</button>
          <button @click="exportAs('csv')"><u-icon name="dl" />CSV 数据</button>
        </u-dropdown>
      </template>
    </u-page-header>

    <div class="wg">
      <div class="wg-b">
        <div class="chips" style="margin-bottom: 13px">
          <button
            v-for="(cfg, key) in DIMS"
            :key="key"
            :class="{ on: activeDim === key }"
            @click="activeDim = key"
          >
            <span class="cdot" :style="{ background: cfg.color }" />{{ cfg.label }}
          </button>
        </div>
        <u-line-chart
          :series="histSeries"
          :labels="histLabels"
          :height="300"
          zoom
          :tip-fmt="(v) => `${v.toFixed(1)}${DIMS[activeDim].unit}`"
        />
      </div>
    </div>

    <div class="grid" style="margin-bottom: 0">
      <div class="wg t4">
        <div class="wg-h">
          <u-icon name="hist" />
          <h3>区间统计</h3>
        </div>
        <div class="wg-b">
          <div class="kvrow kvline">
            <span class="muted small">均值</span><span class="small num">{{ histStats.avg }}</span>
          </div>
          <div class="kvrow kvline">
            <span class="muted small">峰值</span><span class="small num">{{ histStats.max }}</span>
          </div>
          <div class="kvrow">
            <span class="muted small">采样点</span><span class="small num">{{ histStats.n }}</span>
          </div>
        </div>
      </div>

      <div class="wg t8">
        <div class="wg-h">
          <u-icon name="dl" />
          <h3>导出格式</h3>
        </div>
        <div class="wg-b">
          <div class="chips">
            <u-dropdown v-model="fmtOpen.md" :min-width="130">
              <template #trigger>
                <button class="btn sm">Markdown</button>
              </template>
              <button><u-icon name="dl" />立即下载</button>
            </u-dropdown>
            <u-dropdown v-model="fmtOpen.html" :min-width="130">
              <template #trigger>
                <button class="btn sm">HTML</button>
              </template>
              <button><u-icon name="dl" />立即下载</button>
            </u-dropdown>
            <u-dropdown v-model="fmtOpen.csv" :min-width="130">
              <template #trigger>
                <button class="btn sm">CSV</button>
              </template>
              <button><u-icon name="dl" />立即下载</button>
            </u-dropdown>
          </div>
          <div class="small muted" style="margin-top: 10px">
            导出为当前维度 × 当前区间的历史健康报告
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
