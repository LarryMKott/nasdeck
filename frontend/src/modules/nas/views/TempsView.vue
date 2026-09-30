<script setup>
/** 温度监控：关键传感器速览磁贴 + 温度墙（45/60 分档着色，后端 + 演示回退） */
import { computed, ref } from 'vue';
import { temps as mockTemps } from '../mock';
import { walk } from '../utils/series';
import { tempClass } from '../utils/format';
import { useViewData } from '../composables/useViewData';
import * as nasData from '../api/data';
import UPageHeader from '../components/UPageHeader.vue';
import USpark from '../components/USpark.vue';

defineOptions({ name: 'NasTemps' });

/** 温度墙分档阈值：45 偏高 / 60 过热 */
const warmAt = 45;
const hotAt = 60;

const { data: d, live } = useViewData(nasData.fetchTemps, mockTemps);

const headerTag = computed(() => ({
  type: live.value ? 'ok' : 'acc',
  text: live.value ? '正常' : '演示数据',
}));

/** 磁贴 spark（演示形态；真实数据 5s 级轮询时由数值刷新体现） */
const sparkSeeds = { tcpu: 21, tboard: 22, tnvme: 23, traid: 24, tother: 25 };
const sparkData = computed(() =>
  Object.fromEntries(
    d.value.tiles.map((t, i) => {
      const base = Math.max(t.tempC, 1);
      const key = sparkSeeds[t.key] !== undefined ? t.key : 'tother';
      return [t.key, walk(40, sparkSeeds[key] + i, base, base * 0.04, base * 0.9, base * 1.15)];
    })
  )
);

const autoRefresh = ref(true);
</script>

<template>
  <section>
    <u-page-header
      title="温度监控"
      sub="关键传感器速览 · 温度墙"
      :tag="headerTag"
      updated="10:32:10"
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
