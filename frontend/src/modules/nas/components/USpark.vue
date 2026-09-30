<script setup>
/** UNRAID 稿迷你走势线（磁贴内 sparkline） */
import { onActivated, onMounted, ref, watch } from 'vue';
import { renderSpark } from '../utils/chart';

defineOptions({ name: 'USpark' });

const props = defineProps({
  /** 序列数据 */
  data: { type: Array, required: true },
  /** 线色 */
  color: { type: String, required: true },
});

const host = ref(null);

function draw() {
  if (host.value && host.value.clientWidth > 0) renderSpark(host.value, props.data, props.color);
}

onMounted(draw);
onActivated(draw);
watch(() => props.data, draw, { deep: true });
</script>

<template>
  <div ref="host" class="spark" />
</template>

<style scoped>
.spark {
  height: 30px;
  margin-top: 8px;
}
</style>
