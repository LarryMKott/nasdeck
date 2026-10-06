<script setup>
/** 时光机（脑洞 C）：总览页回放模式——拖时间轴查看任意历史时刻的关键指标快照。
 * 数据源 /monitor/history（三级粒度，后端聚合）；打开时拉序列，拖动即时换算；
 * 播放键自动步进；关闭恢复实时。与实时流互斥（回放中磁贴数字不动，面板自渲染）。 */
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { getHistory } from '../api/endpoints/monitor';
import UIcon from './UIcon.vue';

defineOptions({ name: 'UTimeMachine' });

const RANGES = [
  { key: '24h', label: '24 小时' },
  { key: '7d', label: '7 天' },
  { key: '30d', label: '30 天' },
];

const open = ref(false);
const loading = ref(false);
const rangeKey = ref('24h');
const points = ref([]);
const idx = ref(0);
const playing = ref(false);
let playTimer = null;

async function load() {
  loading.value = true;
  try {
    const resp = await getHistory(rangeKey.value);
    points.value = resp?.points ?? [];
    idx.value = Math.max(0, points.value.length - 1);
  } catch {
    points.value = [];
  } finally {
    loading.value = false;
  }
}

function toggle(v) {
  open.value = v ?? !open.value;
  if (open.value && !points.value.length) load();
  if (!open.value) stopPlay();
}

function stopPlay() {
  playing.value = false;
  clearInterval(playTimer);
  playTimer = null;
}

function togglePlay() {
  if (playing.value) return stopPlay();
  if (!points.value.length) return;
  playing.value = true;
  playTimer = setInterval(() => {
    if (idx.value >= points.value.length - 1) return stopPlay();
    idx.value += 1;
  }, 260);
}

watch(rangeKey, () => {
  stopPlay();
  load();
});
onBeforeUnmount(stopPlay);

const point = computed(() => points.value[idx.value] ?? null);
const tsText = computed(() => {
  const ts = point.value?.ts;
  if (!ts) return '—';
  const dt = new Date(`${ts.replace(' ', 'T')}Z`);
  return Number.isNaN(dt.getTime())
    ? ts
    : dt.toLocaleString('zh-CN', {
        month: 'numeric',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
});

/** 快照指标（— 为该桶无采样） */
const stats = computed(() => {
  const p = point.value;
  const f = (v, digits = 0) =>
    v == null ? '—' : (Math.round(v * 10 ** digits) / 10 ** digits).toFixed(digits);
  return [
    { label: 'CPU', value: f(p?.cpu_avg), unit: '%' },
    { label: '内存', value: p?.mem_avg_mb != null ? f(p.mem_avg_mb / 1024, 1) : '—', unit: ' GB' },
    { label: '最高温', value: f(p?.temp_max_c, 1), unit: ' °C' },
    { label: '网速', value: f(p?.net_avg_kbps), unit: ' KB/s' },
    { label: '磁盘读', value: f(p?.disk_read_kbps), unit: ' KB/s' },
    { label: '磁盘写', value: f(p?.disk_write_kbps), unit: ' KB/s' },
  ];
});

const granularityText = computed(
  () =>
    ({ raw: '秒级', '1m': '分钟级', '10m': '10 分钟级' })[point.value?.granularity] ||
    point.value?.granularity ||
    ''
);

defineExpose({ toggle });
</script>

<template>
  <button class="btn sm" :class="{ pri: open }" :disabled="loading" @click="toggle()">
    <u-icon name="hist" />{{ loading ? '加载中…' : open ? '退出时光机' : '时光机' }}
  </button>

  <teleport to="body">
    <div v-if="open" class="tm">
      <div class="tm-panel">
        <div class="tm-head">
          <span class="tm-title"><u-icon name="hist" /> 时光机 · 回放</span>
          <div class="chips">
            <button
              v-for="r in RANGES"
              :key="r.key"
              :class="{ on: rangeKey === r.key }"
              @click="rangeKey = r.key"
            >
              {{ r.label }}
            </button>
          </div>
          <button class="btn sm" @click="toggle(false)"><u-icon name="x" />关闭</button>
        </div>

        <div class="tm-stats num">
          <div v-for="s in stats" :key="s.label" class="tm-stat">
            <span class="l">{{ s.label }}</span>
            <b :class="{ muted: s.value === '—' }">{{ s.value }}</b
            ><i>{{ s.value === '—' ? '' : s.unit }}</i>
          </div>
        </div>

        <div class="tm-slider">
          <button class="btn sm" :disabled="!points.length" @click="togglePlay">
            <u-icon :name="playing ? 'stop' : 'play'" />{{ playing ? '暂停' : '播放' }}
          </button>
          <input
            v-model.number="idx"
            type="range"
            min="0"
            :max="Math.max(0, points.length - 1)"
            :disabled="!points.length"
          />
          <span class="num ts"
            >{{ tsText }}<template v-if="granularityText"> · {{ granularityText }}</template></span
          >
        </div>
        <div v-if="!points.length && !loading" class="small muted" style="margin-top: 8px">
          该区间暂无历史采样（—）：接入时间越久回放越完整
        </div>
      </div>
    </div>
  </teleport>
</template>

<style scoped lang="scss">
.tm {
  position: fixed;
  inset: 0;
  z-index: 120;
  pointer-events: none;
}

.tm-panel {
  position: absolute;
  top: 66px;
  left: 50%;
  width: min(860px, 94vw);
  padding: 14px 18px;
  pointer-events: auto;
  background: var(--tt);
  border: 1px solid var(--ttbd);
  border-radius: 12px;
  box-shadow: var(--shadow);
}

.tm-head {
  display: flex;
  gap: 14px;
  align-items: center;
  justify-content: space-between;

  // teleport 到 body 后脱离 .nd，.ico 全局尺寸约束失效——就地兜底防 SVG 膨胀
  .ico {
    width: 14px;
    height: 14px;
  }
}

.tm-title {
  font-weight: 700;
  color: var(--acc);
}

.tm-stats {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
  margin-top: 12px;
}

.tm-stat {
  padding: 10px 12px;
  background: var(--sf2);
  border-radius: 8px;

  .l {
    display: block;
    margin-bottom: 3px;
    font-size: 12px;
    color: var(--tx3);
  }

  b {
    font-size: 22px;
  }

  b.muted {
    color: var(--tx3);
  }

  i {
    margin-left: 4px;
    font-size: 12px;
    font-style: normal;
    color: var(--tx3);
  }
}

.tm-slider {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 13px;

  .ico {
    width: 13px;
    height: 13px;
  }

  input[type='range'] {
    flex: 1;
    accent-color: var(--acc);
  }

  .ts {
    min-width: 168px;
    font-size: 13px;
    color: var(--tx1);
    text-align: right;
  }
}
</style>
