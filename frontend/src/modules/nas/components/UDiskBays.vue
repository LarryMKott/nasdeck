<script setup>
/** 2.5D 硬盘舱位墙（花活二期 I）：纯 CSS 3D 抽屉盘位，零前端依赖。
 * 面板色按实时温度分档（60/75，沿用后端分级）、活动灯按快照 disk_io_devices
 * 的真实 IOPS 闪烁、侧沿厚度按容量；点击盘位翻面看 SMART 摘要迷你卡。
 * RAID 卡虚拟盘等拿不到 diskstats 的盘 LED 恒灭、速率显"—"（不造假）。
 * rAF 只做视差平滑，页面隐藏即停；prefers-reduced-motion 关视差与闪烁。 */
import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  reactive,
  ref,
} from 'vue';
import { useRealtimeStore } from '../stores/realtime';
import { fetchDiskTrend } from '../services/storage';
import { tempClass } from '../utils/format';

defineOptions({ name: 'UDiskBays' });

const props = defineProps({
  /** 盘位清单（父视图适配）：{ device, slot, model, tempC, capacityText, healthText, serial, hoursText, role } */
  disks: { type: Array, default: () => [] },
  /** 温度分档阈值（花活 I 约定沿用后端 60/75 分级） */
  warmAt: { type: Number, default: 60 },
  hotAt: { type: Number, default: 75 },
});

const realtime = useRealtimeStore();
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** 每盘 IO 速率（/proc/diskstats 差分；无数据/演示态为 null → 灯灭 + "—"） */
const iopsMap = computed(() => realtime.snapshot?.disk_io_devices ?? null);

// ---- 视差微倾：rAF 指数平滑逼近目标角度，标签页隐藏时 rAF 自动停 ----
// rotateX 负角度 = 顶边朝观察者倾（俯视抽屉顶面）；正角度会变成仰视、顶面背对
const BASE_RX = -22;
const scene = ref(null);
const tilt = reactive({ rx: BASE_RX, ry: 0 });
let targetTilt = { rx: BASE_RX, ry: 0 };
let rafId = 0;
let lastTs = 0;

function onPointerMove(ev) {
  if (reducedMotion || !scene.value) return;
  const r = scene.value.getBoundingClientRect();
  const nx = (ev.clientX - r.left) / r.width - 0.5;
  const ny = (ev.clientY - r.top) / r.height - 0.5;
  targetTilt = { rx: BASE_RX + ny * 6, ry: nx * 12 };
}

function onPointerLeave() {
  targetTilt = { rx: BASE_RX, ry: 0 };
}

function tick(now) {
  rafId = requestAnimationFrame(tick);
  const dt = lastTs ? Math.min((now - lastTs) / 1000, 0.1) : 0.016;
  lastTs = now;
  const k = 1 - Math.exp(-dt * 6);
  tilt.rx += (targetTilt.rx - tilt.rx) * k;
  tilt.ry += (targetTilt.ry - tilt.ry) * k;
  scene.value?.style.setProperty('--rx', `${tilt.rx.toFixed(2)}deg`);
  scene.value?.style.setProperty('--ry', `${tilt.ry.toFixed(2)}deg`);
}

function startLoop() {
  if (reducedMotion || rafId) return;
  lastTs = 0;
  rafId = requestAnimationFrame(tick);
}

function stopLoop() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = 0;
}

onMounted(() => {
  realtime.acquire();
  startLoop();
});
onBeforeUnmount(() => {
  stopLoop();
  realtime.release();
});
onActivated(startLoop);
onDeactivated(stopLoop);

// ---- 展示推导 ----
/** 容量文本 → 侧沿厚度 px（"4 TB"/"480 G"；解析失败给缺省厚度） */
function depthOf(bay) {
  const m = /([\d.]+)\s*(TB|T|GB|G)\b/i.exec(bay.capacityText || '');
  if (!m) return 16;
  const tb = parseFloat(m[1]) * (m[2].toUpperCase().startsWith('T') ? 1 : 1 / 1000);
  return Math.round(Math.min(12 + tb * 3.5, 34));
}

function bayKey(bay) {
  return bay.device || `slot${bay.slot}`;
}

function gradeClass(bay) {
  return bay.tempC == null ? '' : tempClass(bay.tempC, props.warmAt, props.hotAt);
}

function ioOf(bay) {
  return iopsMap.value?.[bay.device] ?? null;
}

/** IOPS → 闪烁周期：有活动才亮，IOPS 越高闪越快（0.16 ~ 1.4s） */
function ledStyle(v) {
  if (!v || v <= 0) return null;
  return { animationDuration: `${Math.max(0.16, 1.4 - Math.log10(v + 1) * 0.28).toFixed(2)}s` };
}

function rateText(kbps) {
  if (kbps == null) return '—';
  if (kbps < 1024) return `${Math.round(kbps)} KB/s`;
  if (kbps < 1024 ** 2) return `${(kbps / 1024).toFixed(1)} MB/s`;
  return `${(kbps / 1024 ** 2).toFixed(2)} GB/s`;
}

function tempTextClass(tempC) {
  if (tempC == null) return '';
  if (tempC >= props.hotAt) return 't-bad';
  if (tempC >= props.warmAt) return 't-warn';
  return 't-ok';
}

function healthClass(text) {
  const s = String(text || '');
  if (s.includes('故障')) return 'bad';
  if (s.includes('警告')) return 'warn';
  if (s.includes('正常')) return 'ok';
  return '';
}

// ---- 翻面：SMART 摘要迷你卡（健康状态 + 关键属性 sparkline，重映射 30 天） ----
const flipped = reactive({});
const backs = reactive({}); // key → { points, loading }

async function toggleFlip(bay) {
  const key = bayKey(bay);
  flipped[key] = !flipped[key];
  if (!flipped[key] || !bay.device || backs[key]) return;
  backs[key] = { points: [], loading: true };
  try {
    const r = await fetchDiskTrend(bay.device, 'reallocated', 30);
    backs[key] = { points: r.data.points ?? [], loading: false };
  } catch {
    backs[key] = { points: [], loading: false }; // 无趋势为合法真值，显式空态
  }
}

function backOf(bay) {
  return backs[bayKey(bay)] ?? { points: [], loading: false };
}

/** sparkline 坐标（viewBox 0 0 100 30 归一化，与硬盘页趋势同款） */
function sparkPoints(points) {
  if (!points || points.length < 2) return '';
  const vals = points.map((p) => p.value);
  const min = Math.min(...vals);
  const span = Math.max(...vals) - min || 1;
  return points
    .map((p, i) => `${(i / (points.length - 1)) * 100},${28 - ((p.value - min) / span) * 26}`)
    .join(' ');
}
</script>

<template>
  <div ref="scene" class="bays" @pointermove="onPointerMove" @pointerleave="onPointerLeave">
    <div v-if="!disks.length" class="small muted">{{ t('暂无盘位数据（—）') }}</div>
    <div
      v-for="bay in disks"
      :key="bayKey(bay)"
      class="bay"
      :class="gradeClass(bay)"
      :style="{ '--d': `${depthOf(bay)}px` }"
      @click="toggleFlip(bay)"
    >
      <div class="tray" :class="{ flip: flipped[bayKey(bay)] }">
        <!-- 正面：面板（色 = 实时温度分档） -->
        <div class="face front">
          <div class="frow">
            <span class="devname num">#{{ bay.slot ?? '—' }} · {{ bay.device || '—' }}</span>
            <span class="leds">
              <i
                class="led rd"
                :class="{ on: (ioOf(bay)?.read_iops ?? 0) > 0 }"
                :style="ledStyle(ioOf(bay)?.read_iops)"
              />
              <i
                class="led wr"
                :class="{ on: (ioOf(bay)?.write_iops ?? 0) > 0 }"
                :style="ledStyle(ioOf(bay)?.write_iops)"
              />
            </span>
          </div>
          <div class="model">{{ bay.model }}</div>
          <div class="io-row num">
            <span :class="tempTextClass(bay.tempC)">{{
              bay.tempC != null ? `${bay.tempC} °C` : '—'
            }}</span>
            <span>↓ {{ rateText(ioOf(bay)?.read_kbps) }}</span>
            <span>↑ {{ rateText(ioOf(bay)?.write_kbps) }}</span>
          </div>
          <div class="meta">
            <span v-if="bay.role" class="fsbadge">{{ bay.role }}</span>
            <span class="small muted num">{{ bay.capacityText }}</span>
          </div>
          <i class="handle" />
        </div>
        <!-- 背面：SMART 摘要迷你卡 -->
        <div class="face back">
          <div class="frow">
            <span class="devname num">{{ bay.device || '—' }}</span>
            <span class="st" :class="healthClass(bay.healthText)"
              ><span class="dot" />{{ bay.healthText || '—' }}</span
            >
          </div>
          <div class="small muted num">
            {{
              [bay.serial ? `SN ${bay.serial}` : null, bay.hoursText].filter(Boolean).join(' · ') ||
              '—'
            }}
          </div>
          <div class="spark">
            <svg
              v-if="sparkPoints(backOf(bay).points)"
              viewBox="0 0 100 30"
              preserveAspectRatio="none"
            >
              <polyline
                :points="sparkPoints(backOf(bay).points)"
                fill="none"
                stroke="var(--acc)"
                stroke-width="1.4"
                vector-effect="non-scaling-stroke"
              />
            </svg>
            <span v-else-if="!backOf(bay).loading" class="small muted">{{
              t('暂无趋势数据（—）')
            }}</span>
          </div>
          <div class="small muted">{{ t('近 30 天重映射扇区 · 1h 桶') }}</div>
        </div>
        <!-- 顶面 / 左右侧沿：抽屉厚度（厚度 ∝ 容量） -->
        <i class="face top" />
        <i class="face side r" />
        <i class="face side l" />
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.bays {
  --rx: -22deg;
  --ry: 0deg;

  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(172px, 1fr));
  gap: 20px 16px;
  padding: 8px 4px 12px;
  perspective: 1100px;

  .bay {
    height: 122px;
    cursor: pointer;
    transform: rotateX(var(--rx)) rotateY(var(--ry));
    transform-style: preserve-3d;

    &.warm .front {
      background: var(--warnbg);
      border-color: var(--warn);
    }

    &.hot .front {
      background: var(--badbg);
      border-color: var(--bad);
    }
  }

  .tray {
    position: relative;
    width: 100%;
    height: 100%;
    transform-style: preserve-3d;
    transition: transform 0.55s var(--ease);

    &.flip {
      transform: rotateY(180deg);
    }
  }

  .face {
    position: absolute;
    inset: 0;
    overflow: hidden;
    border-radius: 6px;
    backface-visibility: hidden;
  }

  .front {
    display: flex;
    flex-direction: column;
    gap: 5px;
    padding: 10px 12px 8px;
    background: var(--sf2);
    border: 1px solid var(--bd2);
    box-shadow: 0 12px 24px rgb(0 0 0 / 28%);
    transform: translateZ(calc(var(--d) / 2));
  }

  .back {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px 12px 8px;
    font-size: 12px;
    background: var(--sf3);
    border: 1px solid var(--bd2);
    transform: rotateY(180deg) translateZ(calc(var(--d) / 2));
  }

  // 顶/侧面：同一盒体的厚度面（烘焙式暗色，不随温度分档）。
  // 贴边定位 + transform-origin 旋转：盒体高 ≠ 厚，不能用立方体「居中面」公式
  .top {
    top: 0;
    height: var(--d);
    background: color-mix(in srgb, var(--sf3) 82%, #000);
    border: 1px solid var(--bd2);
    transform: translateZ(calc(var(--d) / -2)) rotateX(90deg);
    transform-origin: 50% 0;
  }

  .side {
    position: absolute;
    top: 0;
    width: var(--d);
    background: color-mix(in srgb, var(--sf3) 66%, #000);
    border: 1px solid var(--bd2);

    // 视差左偏只见右面、右偏只见左面，两面都画避免穿帮
    &.r {
      right: 0;
      left: auto; // inset:0 会过度约束（left 优先于 right），显式放开 left 贴右缘
      transform: translateZ(calc(var(--d) / -2)) rotateY(90deg);
      transform-origin: 100% 50%;
    }

    &.l {
      right: auto;
      left: 0;
      transform: translateZ(calc(var(--d) / -2)) rotateY(-90deg);
      transform-origin: 0 50%;
    }
  }

  .frow {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
  }

  .devname {
    font-size: 13px;
    font-weight: 600;
  }

  .model {
    overflow: hidden;
    font-size: 12px;
    color: var(--tx2);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .io-row {
    display: flex;
    gap: 10px;
    font-size: 12px;
  }

  .meta {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-top: auto;
  }

  .handle {
    position: absolute;
    right: 12px;
    bottom: 9px;
    width: 34px;
    height: 5px;
    background: var(--bd);
    border-radius: 3px;
  }

  .spark {
    display: flex;
    align-items: center;
    height: 34px;

    svg {
      width: 100%;
      height: 100%;
    }
  }

  .st {
    &.warn {
      color: var(--warn);
    }

    &.bad {
      color: var(--bad);
    }

    &.ok {
      color: var(--ok);
    }
  }

  .leds {
    display: inline-flex;
    gap: 5px;
  }

  .led {
    width: 8px;
    height: 8px;
    background: var(--sf3);
    border: 1px solid var(--bd2);
    border-radius: 50%;
    opacity: 0.35;

    &.rd.on {
      background: var(--ok);
      border-color: var(--ok);
      animation: bay-led 1s infinite;
    }

    &.wr.on {
      background: var(--warn);
      border-color: var(--warn);
      animation: bay-led 1s infinite;
    }
  }
}

@keyframes bay-led {
  0%,
  100% {
    box-shadow: 0 0 6px currentcolor;
    opacity: 1;
  }

  50% {
    box-shadow: none;
    opacity: 0.25;
  }
}

@media (prefers-reduced-motion: reduce) {
  .bays {
    .tray {
      transition: none;
    }

    .led.on {
      opacity: 1;
      animation: none;
    }
  }
}
</style>
