<script setup>
/** 温度监控：关键传感器速览磁贴 + 温度墙（45/60 分档着色，后端 + 演示回退） */
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue';
import { temps as mockTemps } from '../mock';
import { tempClass } from '../utils/format';
import { useViewData } from '../composables/useViewData';
import * as nasData from '../api/data';
import UPageHeader from '../components/UPageHeader.vue';
import USpark from '../components/USpark.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasTemps' });

/** 温度墙分档阈值：45 偏高 / 60 过热 */
const warmAt = 45;
const hotAt = 60;

const { data: d, live, refresh, lastUpdated } = useViewData(nasData.fetchTemps, mockTemps);

const headerTag = computed(() => ({
  type: live.value ? 'ok' : 'acc',
  text: live.value ? '正常' : '演示数据',
}));

/** 磁贴 spark：真实温度滚动缓冲（页内按 5s 轮询累积，约 40 点窗口） */
const history = ref({}); // key → number[]
watch(
  d,
  (val) => {
    for (const t of val.tiles ?? []) {
      const arr = history.value[t.key] ?? [];
      arr.push(t.tempC);
      if (arr.length > 40) arr.shift();
      history.value = { ...history.value, [t.key]: arr };
    }
  },
  { immediate: true, deep: true }
);
const sparkData = computed(() =>
  Object.fromEntries(
    d.value.tiles.map((t) => {
      const arr = history.value[t.key] ?? [];
      return [t.key, arr.length > 1 ? arr : [t.tempC, t.tempC]];
    })
  )
);

const autoRefresh = ref(true);
let timer = null;
// keep-alive 路由：定时器随 activated/deactivated 启停（onBeforeUnmount 不触发）
function startTimer() {
  if (timer) return;
  timer = setInterval(() => {
    if (autoRefresh.value) refresh();
  }, 5000);
}

function stopTimer() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

onMounted(startTimer);
onBeforeUnmount(stopTimer);
onActivated(startTimer);
onDeactivated(stopTimer);
</script>

<template>
  <section>
    <u-page-header
      title="温度监控"
      sub="关键传感器速览 · 温度墙"
      :tag="headerTag"
      :updated="lastUpdated"
    >
      <template #right>
        <label class="switch" :class="{ on: autoRefresh }" @click="autoRefresh = !autoRefresh">
          <span class="tr" />5s
        </label>
      </template>
    </u-page-header>

    <div class="grid">
      <div v-for="t in d.tiles" :key="t.key" class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon :name="t.icon" />{{ t.label }}</div>
          <div class="big num">{{ t.tempC }}<small>°C</small></div>
          <u-spark :data="sparkData[t.key]" color="#E8734B" />
        </div>
      </div>
    </div>

    <div class="wg" style="margin-bottom: 0">
      <div class="wg-h">
        <u-icon name="temp" />
        <h3>温度墙</h3>
        <span class="x">全部传感器 · 按温度分档着色</span>
      </div>
      <div class="wg-b">
        <div class="temps" style="grid-template-columns: repeat(auto-fill, minmax(126px, 1fr))">
          <div
            v-for="t in d.wall"
            :key="t.label"
            class="temp"
            :class="tempClass(t.tempC, warmAt, hotAt)"
          >
            <div class="n">{{ t.label }}</div>
            <div class="v num">{{ t.tempC }} °C</div>
          </div>
        </div>
        <div class="legend">
          <span><i style="background: var(--sf3)" />&lt; 45 正常</span>
          <span
            ><i style="background: var(--warnbg); border: 1px solid var(--warn)" />45 – 60
            偏高</span
          >
          <span
            ><i style="background: var(--badbg); border: 1px solid var(--bad)" />&gt; 60 过热</span
          >
        </div>
      </div>
    </div>
  </section>
</template>
