<script setup>
/** UNRAID 稿折线图（自研 SVG 引擎封装）：十字线 tooltip + 可选 dataZoom 缩放 */
import { onActivated, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { renderLine } from '../utils/chart';

defineOptions({ name: 'ULineChart' });

const props = defineProps({
  /** 序列 [{ name, color, data, dash?, area? }] */
  series: { type: Array, required: true },
  /** x 轴时间标签（与序列等长） */
  labels: { type: Array, required: true },
  /** 图表高度 px */
  height: { type: Number, default: 170 },
  /** 是否显示 dataZoom 缩放条 */
  zoom: { type: Boolean, default: false },
  /** tooltip 数值格式化 */
  tipFmt: { type: Function, default: undefined },
  /** y 轴刻度格式化 */
  yTickFmt: { type: Function, default: undefined },
});

const host = ref(null);
// 渐变 id 需要实例级唯一，避免同页多图的 defs 相互覆盖
let uidSeq = 0;
const uid = `nd-chart-${(uidSeq += 1)}-${Math.random().toString(36).slice(2, 8)}`;
let observer = null;

function draw() {
  if (!host.value || host.value.clientWidth === 0) return;
  renderLine(host.value, {
    series: props.series,
    labels: props.labels,
    height: props.height,
    zoom: props.zoom,
    tipFmt: props.tipFmt,
    yTickFmt: props.yTickFmt,
  });
}

onMounted(() => {
  draw();
  observer = new ResizeObserver(() => draw());
  observer.observe(host.value);
});

// keep-alive 页签切回时容器尺寸可能已变化，重绘一次
onActivated(() => draw());

onBeforeUnmount(() => observer?.disconnect());

watch(
  () => [props.series, props.labels],
  () => draw(),
  { deep: true }
);
</script>

<template>
  <div :id="uid" ref="host" class="chartbox" :style="{ height: `${height}px` }" />
</template>
