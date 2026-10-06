<script setup>
/** 系统资源：CPU/内存/网络/磁盘 IO 四图 + GPU 磁贴 + RAPL 功耗（后端 history + 演示回退） */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { chartColors } from '../utils/themeColors';
import { walk, timeLabels } from '../utils/series';
import { useViewData } from '../composables/useViewData';
import { useRealtimeStore } from '../stores/realtime';
import { fetchSystemCharts } from '../services/monitor';
import { throughputText } from '../services/dashboard';
import UPageHeader from '../components/UPageHeader.vue';
import ULineChart from '../components/ULineChart.vue';
import USpark from '../components/USpark.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasSystem' });

/** 演示回退序列（后端不可达时保持页面完整）——形状与真实链路一致：单聚合序列 */
const fallbackLabels = timeLabels(60, 1);
const fallback = {
  labels: fallbackLabels,
  cpuSeries: [
    {
      name: 'CPU',
      get color() {
        return chartColors.value.acc;
      },
      data: walk(60, 5, 23, 7, 5, 60),
    },
  ],
  memSeries: [
    {
      name: '内存',
      get color() {
        return chartColors.value.info;
      },
      data: walk(60, 6, 41, 2.5, 35, 50),
    },
  ],
  netSeries: [
    {
      name: '总吞吐',
      get color() {
        return chartColors.value.ok;
      },
      data: walk(60, 7, 15, 6, 1, 60),
    },
  ],
  diskSeries: [
    {
      name: '读',
      get color() {
        return chartColors.value.acc;
      },
      data: walk(60, 11, 86, 26, 5, 220),
    },
  ],
};

const { data: charts, live, lastUpdated } = useViewData(fetchSystemCharts, fallback);

const headerTag = computed(() => ({
  type: live.value ? 'ok' : 'acc',
  text: live.value ? '正常' : '演示数据',
}));
const autoRefresh = ref(true);

/** 实时磁贴：WS/轮询快照直接驱动内存与磁盘 IO 卡头 */
const realtime = useRealtimeStore();
onMounted(() => realtime.acquire());
onBeforeUnmount(() => realtime.release());

const memText = computed(() => {
  const snap = realtime.snapshot;
  if (!snap) return '41% · 26.2/64 GB';
  return `${snap.mem_percent}% · ${(snap.mem_used_mb / 1024).toFixed(1)}/${(snap.mem_total_mb / 1024).toFixed(0)} GB`;
});
const memPercent = computed(() => realtime.snapshot?.mem_percent ?? 41);
const diskText = computed(() => {
  const io = realtime.snapshot?.disk_io;
  if (!io) return '读 86 · 写 42 MB/s';
  return `读 ${throughputText(io.read_kbps ?? 0)} · 写 ${throughputText(io.write_kbps ?? 0)}`;
});

/** CPU 卡头：实时使用率替代写死的 23% */
const cpuText = computed(() => {
  const v = realtime.snapshot?.cpu_percent;
  return v == null ? '— % · 60s 窗口' : `${Math.round(v * 10) / 10}% · 60s 窗口`;
});
const cpuMeterPct = computed(() => {
  const v = realtime.snapshot?.cpu_percent;
  return v == null ? 0 : Math.min(100, Math.max(0, v));
});

/** GPU 磁贴：实时使用率 + 滚动 spark（无卡/不可用为 0 平线） */
const gpuHistory = ref([]);
watch(
  () => realtime.snapshot,
  (snap) => {
    if (!snap) return;
    const gpu = snap.gpu;
    const now = new Date();
    const pad = (x) => String(x).padStart(2, '0');
    gpuHistory.value.push({
      label: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
      percent: gpu && gpu.available ? Math.round(gpu.percent ?? 0) : 0,
    });
    if (gpuHistory.value.length > 40) gpuHistory.value.shift();
  }
);
const gpuSparkData = computed(() => gpuHistory.value.map((p) => p.percent));
const gpuPercent = computed(() => gpuHistory.value.at(-1)?.percent ?? 0);

/** RAPL 功耗：实时 power 分量（非 Intel 平台显示 —） */
const powerW = computed(() => {
  const p = realtime.snapshot?.power;
  return p && p.available ? Math.round((p.watts ?? 0) * 10) / 10 : '—';
});
const cpuW = computed(() => {
  const p = realtime.snapshot?.power;
  return p && p.available && p.cpu_w != null ? Math.round(p.cpu_w * 10) / 10 : '—';
});
const dramW = computed(() => {
  const p = realtime.snapshot?.power;
  return p && p.available && p.dram_w != null ? Math.round(p.dram_w * 10) / 10 : '—';
});
</script>

<template>
  <section>
    <u-page-header
      title="系统资源"
      sub="CPU · 内存 · 网络 · 磁盘 IO · GPU"
      :tag="headerTag"
      :updated="lastUpdated"
    >
      <template #right>
        <label class="switch" :class="{ on: autoRefresh }" @click="autoRefresh = !autoRefresh">
          <span class="tr" />1s
        </label>
      </template>
    </u-page-header>

    <div class="grid">
      <div class="wg t6">
        <div class="wg-h">
          <u-icon name="cpu" />
          <h3>CPU 使用率</h3>
          <span class="x num">{{ cpuText }}</span>
        </div>
        <div class="wg-b">
          <div class="meter" style="margin-bottom: 10px">
            <i class="c-ok" :style="{ width: `${cpuMeterPct}%` }" />
          </div>
          <u-line-chart
            :series="charts.cpuSeries"
            :labels="charts.labels"
            :height="170"
            :tip-fmt="(v) => `${v.toFixed(1)}%`"
            :y-tick-fmt="(v) => `${v}%`"
          />
        </div>
      </div>

      <div class="wg t6">
        <div class="wg-h">
          <u-icon name="server" />
          <h3>内存</h3>
          <span class="x num">{{ memText }}</span>
        </div>
        <div class="wg-b">
          <div class="meter" style="margin-bottom: 10px">
            <i class="c-info" :style="{ width: `${memPercent}%` }" />
          </div>
          <u-line-chart
            :series="charts.memSeries"
            :labels="charts.labels"
            :height="170"
            :tip-fmt="(v) => `${v.toFixed(1)}%`"
            :y-tick-fmt="(v) => `${v}%`"
          />
        </div>
      </div>

      <div class="wg t6">
        <div class="wg-h">
          <u-icon name="net" />
          <h3>网络</h3>
          <span class="x">全网聚合</span>
        </div>
        <div class="wg-b">
          <u-line-chart
            :series="charts.netSeries"
            :labels="charts.labels"
            :height="170"
            :tip-fmt="(v) => `${v.toFixed(0)} KB/s`"
          />
        </div>
      </div>

      <div class="wg t6">
        <div class="wg-h">
          <u-icon name="drive" />
          <h3>磁盘 IO</h3>
          <span class="x num">{{ diskText }}</span>
        </div>
        <div class="wg-b">
          <u-line-chart
            :series="charts.diskSeries"
            :labels="charts.labels"
            :height="170"
            :tip-fmt="(v) => `${v.toFixed(0)} KB/s`"
          />
        </div>
      </div>
    </div>

    <div class="grid" style="margin-bottom: 0">
      <div class="wg t4 tile-wg">
        <div class="wg-b">
          <div class="cap"><u-icon name="pulse" />GPU 使用率</div>
          <div class="big num">{{ gpuPercent }}<small>%</small></div>
          <u-spark :data="gpuSparkData" :color="chartColors.gpu" />
        </div>
      </div>

      <div class="wg t8">
        <div class="wg-h">
          <u-icon name="power" />
          <h3>RAPL 功耗</h3>
          <span class="x">Running Average Power Limit</span>
        </div>
        <div class="wg-b">
          <div class="kv2" style="grid-template-columns: 1fr 1fr 1fr">
            <div class="kvrow kvline">
              <span class="muted small">CPU Package</span
              ><span class="small num">{{ cpuW }} W</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">DRAM</span><span class="small num">{{ dramW }} W</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">合计</span>
              <span class="small num" style="font-weight: 700; color: var(--acc)"
                >{{ powerW }} W</span
              >
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
