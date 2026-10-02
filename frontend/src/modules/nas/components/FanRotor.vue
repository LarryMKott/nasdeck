<script setup>
/**
 * 风扇转子：SVG 重画（外壳环 + 7 曲叶 + 轴帽），角度由传感器 RPM 积分驱动。
 *
 * 平滑策略：目标 RPM 经指数平滑（τ≈1.2s）再积分角度（rAF 每帧
 * angle += rpm/60*360*dt），变速时相位连续无跳变——CSS animation-duration
 * 方案改时长会重启动画导致肉眼可见的跳帧，故弃用。
 * rpm=0 平滑减速停转；系统「减少动态效果」偏好时不转。
 */
import { onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue';

defineOptions({ name: 'FanRotor' });

const props = defineProps({
  /** 传感器转速（RPM）；0 停转。无转速计通道由父级按占空比估算传入 */
  rpm: { type: Number, default: 0 },
  /** 满速基准（动态模糊强度归一用） */
  maxRpm: { type: Number, default: 2000 },
  /** 尺寸 class：mini（15px）| lg（30px） */
  size: { type: String, default: 'mini' },
});

const bladesRef = ref(null);
const sheenRef = ref(null);

const TAU_S = 1.2; // 平滑时间常数
const BLADES = 7;

let rafId = 0;
let fallbackId = 0;
let lastFrameAt = 0;
let lastTs = 0;
let shownRpm = 0; // 平滑后的显示转速
let angle = 0; // 连续相位（deg，取模只防浮点无限增长）
let running = false;

const reducedMotion =
  typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

function frame(ts) {
  const dt = Math.min((ts - lastTs) / 1000, 0.25); // 隐藏页回来防大步长
  lastTs = ts;
  lastFrameAt = performance.now();
  const target = reducedMotion ? 0 : Math.max(0, props.rpm || 0);
  shownRpm += (target - shownRpm) * (1 - Math.exp(-dt / TAU_S));
  if (Math.abs(target - shownRpm) < 0.5) shownRpm = target;
  angle = (angle + (shownRpm / 60) * 360 * dt) % 360;
  if (bladesRef.value) {
    bladesRef.value.style.transform = `rotate(${angle.toFixed(2)}deg)`;
    // 高速“动态模糊”：转速越高叶片越淡
    bladesRef.value.style.opacity = String(
      1 - Math.min(1, shownRpm / Math.max(props.maxRpm, 1)) * 0.4
    );
  }
  if (sheenRef.value) {
    sheenRef.value.style.opacity = String(Math.min(1, shownRpm / Math.max(props.maxRpm, 1)) * 0.14);
  }
  if (shownRpm <= 0 && target <= 0) {
    running = false; // 停稳即停循环，rpm 变化时重启
    return;
  }
  rafId = requestAnimationFrame(frame);
}

function ensureLoop() {
  if (running) return;
  running = true;
  lastTs = performance.now();
  lastFrameAt = lastTs;
  rafId = requestAnimationFrame(frame);
}

/** rAF 兜底：遮挡/省电场景浏览器整体暂停 rAF，10Hz 定时器仅在停摆时接手
 * （rAF 恢复后 lastFrameAt 每帧刷新，兜底自动休眠，不会双重驱动） */
function fallbackTick() {
  if (!running || performance.now() - lastFrameAt <= 200) return;
  frame(performance.now());
}

onMounted(() => {
  ensureLoop();
  fallbackId = setInterval(fallbackTick, 100);
});
// keep-alive 下 onBeforeUnmount 不触发：隐藏页停掉 rAF 与兜底定时器，回来再启
onDeactivated(() => {
  running = false;
  cancelAnimationFrame(rafId);
  if (fallbackId) {
    clearInterval(fallbackId);
    fallbackId = 0;
  }
});
onActivated(() => {
  ensureLoop();
  if (!fallbackId) fallbackId = setInterval(fallbackTick, 100);
});
watch(
  () => props.rpm,
  () => ensureLoop()
);
onBeforeUnmount(() => {
  cancelAnimationFrame(rafId);
  clearInterval(fallbackId);
});
</script>

<template>
  <svg
    class="nd-fan-rotor"
    :class="size === 'mini' ? 'mini' : 'lg'"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    <defs>
      <linearGradient id="nd-fan-blade" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#4a4d58" />
        <stop offset="1" stop-color="#26282f" />
      </linearGradient>
    </defs>
    <!-- 外壳环 -->
    <circle cx="12" cy="12" r="10.7" fill="var(--sf1)" stroke="var(--bd)" stroke-width="1" />
    <!-- 7 曲叶：rAF 驱动旋转（style.transform 直接写，不走 Vue 渲染管线） -->
    <g ref="bladesRef" style="transform-origin: 12px 12px">
      <path
        v-for="i in BLADES"
        :key="i"
        d="M12 12C11.5 8.9 12.4 5.8 15.1 4.4c1.3 2.5.8 5.5-1.6 7.3-.5.4-1 .6-1.5.3Z"
        :transform="`rotate(${((i - 1) * 360) / BLADES} 12 12)`"
        fill="url(#nd-fan-blade)"
        stroke="var(--bd)"
        stroke-width="0.3"
      />
    </g>
    <!-- 高速光晕（透明度∝转速） -->
    <circle ref="sheenRef" cx="12" cy="12" r="9.5" fill="var(--acc)" opacity="0" />
    <!-- 轴帽（静止层压在叶片上） -->
    <circle cx="12" cy="12" r="2.7" fill="#2b2d35" stroke="var(--bd)" stroke-width="0.8" />
    <circle cx="12" cy="12" r="0.9" fill="var(--acc)" />
  </svg>
</template>

<style scoped>
.nd-fan-rotor {
  display: block;
}

.nd-fan-rotor.mini {
  width: 15px;
  height: 15px;
}

.nd-fan-rotor.lg {
  width: 30px;
  height: 30px;
}
</style>
