<script setup>
/** 温度监控：速览磁贴 + 温度墙 / 机箱热力图（花活 F），5s 轮询，后端 + 演示回退 */
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue';
import { temps as mockTemps } from '../mock';
import { tempClass } from '../utils/format';
import { useViewData } from '../composables/useViewData';
import { fetchChassis, fetchTemps } from '../services/monitor';
import { useRealtimeStore } from '../stores/realtime';
import UPageHeader from '../components/UPageHeader.vue';
import USpark from '../components/USpark.vue';
import UChassis from '../components/UChassis.vue';
import UChassis3D from '../components/UChassis3D.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasTemps' });

/** 温度墙分档阈值：45 偏高 / 60 过热 */
const warmAt = 45;
const hotAt = 60;

/** 视图模式：速览（磁贴+温度墙）/ 立体（等距机箱，三期 R1）/ 机箱（2D 热力图），记忆上次选择 */
const MODE_KEY = 'nd_temps_mode';
const _modeRaw = localStorage.getItem(MODE_KEY);
const mode = ref(['quick', 'iso', 'chassis'].includes(_modeRaw) ? _modeRaw : 'quick');

// 立体机箱实时分量：每盘 IO / 每网口吞吐 / RAPL 功耗 / GPU 可用（realtime 快照）
const realtime = useRealtimeStore();
onMounted(() => realtime.acquire());
onBeforeUnmount(() => realtime.release());
const ioMap = computed(() => realtime.snapshot?.disk_io_devices ?? null);
const netMap = computed(() => realtime.snapshot?.net ?? null);
const powerSnap = computed(() => realtime.snapshot?.power ?? null);
const gpuOn = computed(() => !!realtime.snapshot?.gpu?.available);
function setMode(m) {
  if (mode.value === m) return;
  mode.value = m;
  localStorage.setItem(MODE_KEY, m);
  refresh(); // 立即拉取新形态数据，不等下一轮 5s
}

// 两种形态取数器不同（机箱还需风区+硬盘），按模式分发
const {
  data: d,
  live,
  refresh,
  lastUpdated,
} = useViewData(() => (mode.value === 'quick' ? fetchTemps() : fetchChassis()), mockTemps);

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
      :title="t('温度监控')"
      :sub="t('关键传感器速览 · 温度墙')"
      :tag="headerTag"
      :updated="lastUpdated"
    >
      <template #right>
        <div class="seg">
          <button :class="{ on: mode === 'quick' }" @click="setMode('quick')">
            {{ t('速览') }}
          </button>
          <button :class="{ on: mode === 'iso' }" @click="setMode('iso')">
            {{ t('立体') }}
          </button>
          <button :class="{ on: mode === 'chassis' }" @click="setMode('chassis')">
            {{ t('机箱') }}
          </button>
        </div>
        <label class="switch" :class="{ on: autoRefresh }" @click="autoRefresh = !autoRefresh">
          <span class="tr" />5s
        </label>
      </template>
    </u-page-header>

    <!-- 立体机箱（三期 R1）：inventory × 模板 → layout → 等距 SVG 渲染器 -->
    <template v-if="mode === 'iso'">
      <u-chassis3-d
        :sensors="d.sensors ?? []"
        :fans="d.fans ?? []"
        :disks="d.disks ?? []"
        :board="d.board ?? null"
        :dimms="d.dimms ?? 2"
        :nics="d.nics ?? 1"
        :io="ioMap"
        :net="netMap"
        :power="powerSnap"
        :gpu-available="gpuOn"
        :warm-at="60"
        :hot-at="75"
        @jump="refresh"
      />
    </template>

    <template v-if="mode === 'chassis'">
      <u-chassis
        :sensors="d.sensors ?? []"
        :fans="d.fans ?? []"
        :disks="d.disks ?? []"
        :warm-at="warmAt"
        :hot-at="hotAt"
      />
    </template>

    <template v-else>
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
          <h3>{{ t('温度墙') }}</h3>
          <span class="x">{{ t('全部传感器 · 按温度分档着色') }}</span>
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
              ><i style="background: var(--badbg); border: 1px solid var(--bad)" />&gt; 60
              过热</span
            >
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.seg {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--bd2);
  border-radius: 6px;

  button {
    height: 28px;
    padding: 0 12px;
    font-size: 13px;
    color: var(--tx2);
    background: transparent;
    border: none;
    transition: all var(--t) var(--ease);

    &.on {
      color: #fff;
      background: var(--acc);
    }

    &:hover:not(.on) {
      color: var(--acc);
    }
  }
}
</style>
