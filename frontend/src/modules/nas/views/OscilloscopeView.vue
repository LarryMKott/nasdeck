<script setup>
/** 多通道示波器（脑洞 D）：WS realtime 1s 流 → 环形缓冲 → canvas 荧光滚动波形。
 * 通道独立自动量程；支持暂停/时间窗切换/游标读数；页面隐藏或 keep-alive
 * 离开时停 rAF（与停轮询约定一致）。数据零新增采集——复用既有 WS 快照。 */
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue';
import { useRealtimeStore } from '../stores/realtime';
import { chartColors } from '../utils/themeColors';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasScope' });

/** 通道定义：色板取主题图表色（chartColors 响应式，皮肤切换随动） */
const CHANNELS = [
  {
    key: 'cpu',
    label: 'CPU %',
    get color() {
      return chartColors.value.acc;
    },
    get: (s) => s.cpu_percent,
  },
  {
    key: 'mem',
    label: '内存 %',
    get color() {
      return chartColors.value.info;
    },
    get: (s) => s.mem_percent,
  },
  {
    key: 'netrx',
    label: '网速 ↓ KB/s',
    get color() {
      return chartColors.value.ok;
    },
    get: (s) => sumNet(s, 'rx_kbps'),
  },
  {
    key: 'nettx',
    label: '网速 ↑ KB/s',
    get color() {
      return chartColors.value.warn;
    },
    get: (s) => sumNet(s, 'tx_kbps'),
  },
  {
    key: 'dio_r',
    label: '磁盘 读 KB/s',
    get color() {
      return chartColors.value.purp;
    },
    get: (s) => s.disk_io?.read_kbps ?? null,
  },
  {
    key: 'dio_w',
    label: '磁盘 写 KB/s',
    get color() {
      return chartColors.value.bad || '#e5484d';
    },
    get: (s) => s.disk_io?.write_kbps ?? null,
  },
  {
    key: 'gpu',
    label: 'GPU %',
    get color() {
      return chartColors.value.gpu;
    },
    get: (s) => (s.gpu?.available ? s.gpu.percent : null),
  },
];

function sumNet(s, key) {
  return Object.values(s.net ?? {}).reduce((a, v) => a + (v[key] ?? 0), 0);
}

const enabled = ref(new Set(['cpu', 'mem', 'netrx', 'nettx']));
function toggleChannel(key) {
  const next = new Set(enabled.value);
  next.has(key) ? next.delete(key) : next.add(key);
  enabled.value = next;
}

/** 时间窗（秒）：60 / 300 / 900 */
const windowSec = ref(60);
const paused = ref(false);

/** 环形数据：{t, v: {key: value}} 数组，按窗口修剪 */
const points = ref([]);

const realtime = useRealtimeStore();
onMounted(() => realtime.acquire());
onBeforeUnmount(() => {
  realtime.release();
  stopLoop();
});
onActivated(() => startLoop());
onDeactivated(() => stopLoop());

watch(
  () => realtime.snapshot,
  (snap) => {
    if (!snap || paused.value) return;
    const v = {};
    for (const c of CHANNELS) v[c.key] = c.get(snap);
    points.value.push({ t: Date.now(), v });
    const cutoff = Date.now() - Math.max(windowSec.value, 900) * 1000 - 5000;
    while (points.value.length && points.value[0].t < cutoff) points.value.shift();
  }
);

/** 游标：鼠标在画布上的横坐标（null = 不显示） */
const cursorX = ref(null);
const canvasEl = ref(null);

let rafId = 0;
function startLoop() {
  if (rafId) return;
  const draw = () => {
    drawChart();
    rafId = requestAnimationFrame(draw);
  };
  rafId = requestAnimationFrame(draw);
}
function stopLoop() {
  cancelAnimationFrame(rafId);
  rafId = 0;
}
// 标签页隐藏时 rAF 自动停；visibilitychange 恢复由 rAF 语义天然覆盖

function drawChart() {
  const canvas = canvasEl.value;
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (!w || !h) return;
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr;
    canvas.height = h * dpr;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  // 荧光网格
  ctx.strokeStyle = 'rgb(255 255 255 / 6%)';
  ctx.lineWidth = 1;
  for (let y = 0; y <= 4; y++) {
    ctx.beginPath();
    ctx.moveTo(0, (h / 4) * y + 0.5);
    ctx.lineTo(w, (h / 4) * y + 0.5);
    ctx.stroke();
  }
  for (let x = 0; x <= 6; x++) {
    ctx.beginPath();
    ctx.moveTo((w / 6) * x + 0.5, 0);
    ctx.lineTo((w / 6) * x + 0.5, h);
    ctx.stroke();
  }

  const data = points.value;
  if (!data.length) return;
  const winMs = windowSec.value * 1000;
  const tNow = data[data.length - 1].t;
  const t0 = tNow - winMs;
  const xOf = (t) => ((t - t0) / winMs) * w;

  // 游标
  if (cursorX.value != null) {
    ctx.strokeStyle = 'rgb(255 255 255 / 35%)';
    ctx.beginPath();
    ctx.moveTo(cursorX.value + 0.5, 0);
    ctx.lineTo(cursorX.value + 0.5, h);
    ctx.stroke();
  }

  for (const c of CHANNELS) {
    if (!enabled.value.has(c.key)) continue;
    // 窗口内该通道数值 → 自动量程（min 保底 1，避免零基线变成直线重叠轴）
    const vals = [];
    for (const p of data) {
      if (p.t < t0) continue;
      const v = p.v[c.key];
      if (v != null) vals.push(v);
    }
    if (vals.length < 2) continue;
    const max = Math.max(...vals, 1);
    const min = Math.min(...vals, 0);
    const span = max - min || 1;
    ctx.strokeStyle = c.color;
    ctx.lineWidth = 1.6;
    ctx.shadowColor = c.color;
    ctx.shadowBlur = 6; // 荧光辉光
    ctx.beginPath();
    let started = false;
    for (const p of data) {
      if (p.t < t0 || p.v[c.key] == null) continue;
      const x = xOf(p.t);
      const y = h - 6 - ((p.v[c.key] - min) / span) * (h - 24);
      started ? ctx.lineTo(x, y) : (ctx.moveTo(x, y), (started = true));
    }
    ctx.stroke();
    ctx.shadowBlur = 0;
  }
}

/** 游标读数：悬停位置对应时刻的各通道值 */
const cursorVals = computed(() => {
  if (cursorX.value == null) return null;
  const canvas = canvasEl.value;
  if (!canvas) return null;
  const w = canvas.clientWidth;
  const data = points.value;
  if (!data.length) return null;
  const winMs = windowSec.value * 1000;
  const tNow = data[data.length - 1].t;
  const tAt = tNow - winMs + (cursorX.value / w) * winMs;
  let nearest = data[0];
  for (const p of data) if (Math.abs(p.t - tAt) < Math.abs(nearest.t - tAt)) nearest = p;
  return {
    time: new Date(nearest.t).toLocaleTimeString('zh-CN', { hour12: false }),
    vals: CHANNELS.filter((c) => enabled.value.has(c.key)).map((c) => ({
      label: c.label,
      color: c.color,
      text: nearest.v[c.key] != null ? `${Math.round(nearest.v[c.key] * 10) / 10}` : '—',
    })),
  };
});

function onMove(e) {
  const rect = canvasEl.value?.getBoundingClientRect();
  cursorX.value = rect ? e.clientX - rect.left : null;
}
function onLeave() {
  cursorX.value = null;
}

const connText = computed(() => (realtime.connected ? t('实时推送') : t('轮询降级')));
</script>

<template>
  <section>
    <div class="wg">
      <div class="wg-h">
        <u-icon name="power" />
        <h3>多通道示波器</h3>
        <span class="x">
          <span class="tag" :class="realtime.connected ? 'ok' : 'warn'">
            <span class="dot" />{{ connText }}
          </span>
          <button class="btn sm" :class="{ pri: paused }" @click="paused = !paused">
            <u-icon :name="paused ? 'play' : 'stop'" />{{ paused ? '继续' : '暂停' }}
          </button>
        </span>
      </div>
      <div class="wg-b">
        <div class="scope-toolbar">
          <div class="chips">
            <button
              v-for="c in CHANNELS"
              :key="c.key"
              type="button"
              :class="{ on: enabled.has(c.key) }"
              :style="enabled.has(c.key) ? { borderColor: c.color, color: c.color } : {}"
              @click="toggleChannel(c.key)"
            >
              {{ c.label }}
            </button>
          </div>
          <div class="chips">
            <button
              v-for="w in [60, 300, 900]"
              :key="w"
              type="button"
              :class="{ on: windowSec === w }"
              @click="windowSec = w"
            >
              {{ w >= 60 ? `${w / 60} 分钟` : `${w} 秒` }}
            </button>
          </div>
        </div>

        <div class="scope-wrap">
          <canvas ref="canvasEl" class="scope-canvas" @mousemove="onMove" @mouseleave="onLeave" />
          <div v-if="cursorVals" class="scope-cursor num">
            <span class="t">{{ cursorVals.time }}</span>
            <span v-for="v in cursorVals.vals" :key="v.label" :style="{ color: v.color }">
              {{ v.label }} {{ v.text }}
            </span>
          </div>
          <div v-else-if="!points.length" class="scope-empty small muted">
            {{ t('等待实时数据流入（—）：WS 推送或轮询降级接入后开始绘制') }}
          </div>
        </div>
        <div class="small muted" style="margin-top: 10px">
          {{
            t(
              '悬停画布显示游标读数；数据源为 1s 实时快照，页面隐藏或离开本页自动停绘（零常驻开销）。'
            )
          }}
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.scope-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: space-between;
  margin-bottom: 12px;
}

.scope-wrap {
  position: relative;
  height: 380px;
  overflow: hidden;

  // 半透明黑叠在皮肤底色上（写死深色在花活皮肤下像补丁）
  background: rgb(3 5 8 / 45%);
  border: 1px solid var(--bd);
  border-radius: 10px;
}

.scope-canvas {
  display: block;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}

.scope-cursor {
  position: absolute;
  top: 10px;
  left: 12px;
  display: flex;
  gap: 14px;
  padding: 5px 10px;
  font-size: 12px;
  pointer-events: none;
  background: rgb(0 0 0 / 55%);
  border-radius: 6px;

  .t {
    color: var(--tx2);
  }
}

.scope-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
