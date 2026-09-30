<script setup>
/** UNRAID 稿风扇转子图形：三叶几何扇叶，转速由占空比映射动画时长 */
import { computed } from 'vue';

defineOptions({ name: 'FanRotor' });

const props = defineProps({
  /** 动画一周时长（秒），越小越快 */
  durSec: { type: Number, default: 3 },
  /** 停转 */
  paused: { type: Boolean, default: false },
  /** 尺寸 class：mini（15px）| lg（30px） */
  size: { type: String, default: 'mini' },
});

const style = computed(() => ({
  '--d': `${Math.max(0.35, props.durSec)}s`,
  animationPlayState: props.paused ? 'paused' : 'running',
}));
</script>

<template>
  <svg
    class="nd-fan-rotor"
    :class="size === 'mini' ? 'mini' : 'lg'"
    :style="style"
    viewBox="0 0 24 24"
  >
    <path d="M12 12c-.5-3.8-2.2-5.7-4.2-5.1C5.8 7.5 5.4 10 7.3 11.5c1.5 1.1 3.2.7 4.7.5Z" />
    <path
      d="M12 12c3.5 1.7 6.1 1.5 6.7-.6.6-2-1.4-3.6-3.8-2.9-1.7.5-2.5 2.1-2.9 3.5Z"
      transform="rotate(40 12 12)"
    />
    <path
      d="M11.2 13.3c-2.7 2.5-3.4 4.9-2 6.3 1.4 1.4 3.8.7 4.5-1.6.5-1.8-.7-3.3-2.5-4.7Z"
      transform="rotate(-160 12 12)"
    />
    <circle cx="12" cy="12" r="2" fill="var(--sf2)" stroke="none" />
  </svg>
</template>

<style scoped>
.nd-fan-rotor {
  opacity: 0.85;
  fill: var(--acc);
  stroke: none;
  transform-origin: center;
  animation: nd-rotor-spin var(--d, 3s) linear infinite;
  transform-box: fill-box;
}

.nd-fan-rotor.mini {
  width: 15px;
  height: 15px;
}

.nd-fan-rotor.lg {
  width: 30px;
  height: 30px;
}

@keyframes nd-rotor-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
