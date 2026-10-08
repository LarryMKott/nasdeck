<script setup>
/** 总览：UNRAID Dashboard 式磁贴 + GPU 监控 + 风扇/Docker/温度/缓存/告警（后端实时 + 演示回退） */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { chartColors } from '../utils/themeColors';
import { tempClass } from '../utils/format';
import { useViewData } from '../composables/useViewData';
import { useRealtimeStore } from '../stores/realtime';
import {
  applyCpuRealtime,
  applyDiskRealtime,
  applyGpuDetail,
  applyGpuRealtime,
  applyMemRealtime,
  applyNetRealtime,
  applyPowerRealtime,
  applySystemRealtime,
  emptyDashboard,
  fetchDashboard,
} from '../services/dashboard';
import { fetchActiveAlerts } from '../services/automation';
import { downloadStatusCard } from '../utils/statusCard';
import UPageHeader from '../components/UPageHeader.vue';
import UTimeMachine from '../components/UTimeMachine.vue';
import USpark from '../components/USpark.vue';
import ULineChart from '../components/ULineChart.vue';
import FanRotor from '../components/FanRotor.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasDash' });

// 初始空骨架（磁贴显示「—」而非演示值）；mock 仅由适配层在后端不可达时整页回退
const { data: d, live, lastUpdated } = useViewData(fetchDashboard, emptyDashboard());
const { data: alerts } = useViewData(fetchActiveAlerts, []);

/** WS 实时快照合并（仅更新磁贴数字，图表/序列仍走加载时数据） */
const realtime = useRealtimeStore();
onMounted(() => realtime.acquire());
onBeforeUnmount(() => realtime.release());
watch(
  () => realtime.snapshot,
  (snap) => {
    if (!snap || !live.value) return;
    d.value.cpu.percent = Math.round(snap.cpu_percent * 10) / 10;
    applyCpuRealtime(d.value.cpu, snap);
    applyMemRealtime(d.value.mem, snap);
    applyGpuRealtime(d.value.gpu, snap);
    applyNetRealtime(d.value.net, snap);
    applyDiskRealtime(d.value.diskIo, snap);
    applyPowerRealtime(d.value.power, snap);
    applySystemRealtime(d.value.system, snap);
    applyGpuDetail(d.value.gpuDetail, snap);
    const netKbps = Object.values(snap.net ?? {}).reduce(
      (a, v) => a + (v.rx_kbps ?? 0) + (v.tx_kbps ?? 0),
      0
    );
    netHistory.value.push(Math.round(netKbps));
    dioHistory.value.push(
      Math.round((snap.disk_io?.read_kbps ?? 0) + (snap.disk_io?.write_kbps ?? 0))
    );
    if (netHistory.value.length > 40) netHistory.value.shift();
    if (dioHistory.value.length > 40) dioHistory.value.shift();
    const gpuPt = snap.gpu && snap.gpu.available ? Math.round(snap.gpu.percent ?? 0) : 0;
    const now = new Date();
    const pad = (x) => String(x).padStart(2, '0');
    gpuHistory.value.push({
      label: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
      percent: gpuPt,
    });
    if (gpuHistory.value.length > 60) gpuHistory.value.shift();
  }
);

// ---- 状态分享卡片（脑洞 B）：canvas 手绘 PNG，一键下载发群 ----
const cardBusy = ref(false);
function genStatusCard() {
  if (cardBusy.value) return;
  cardBusy.value = true;
  try {
    downloadStatusCard(d.value, {
      diskTemps: (d.value.diskTemps || []).map((t) => ({
        label: t.label,
        celsius: t.tempC ?? t.celsius ?? 0,
      })),
      firingCount: (alerts.value || []).length,
    });
  } finally {
    setTimeout(() => (cardBusy.value = false), 600);
  }
}

const headerTag = computed(() => ({
  type: live.value ? 'ok' : 'acc',
  text: live.value ? t('正常') : t('演示数据'),
}));
const autoRefresh = ref(true);

/** 功耗条比例：按 package 最大量程 65W 归一（i3 级 CPU TDP 上限，非精确标尺） */
const powerMeterPct = computed(() => {
  const w = Number(d.value.power.watts);
  return Number.isFinite(w) ? Math.min(100, Math.max(4, (w / 65) * 100)) : 4;
});

/** CPU 磁贴：每线程 使用率/频率 双视图（WS 1s 快照驱动） */
const cpuMode = ref('usage');
/** 柱条列数随线程数自适应：≤6 铺满一行，更多则两行均分（4 线程 4 列、16 线程 8 列） */
const coreCols = computed(() => {
  const n = (d.value.cpu.cores || []).length;
  if (!n) return 8;
  return n <= 6 ? n : Math.ceil(n / 2);
});
const coreFreqMhz = (i) => {
  const v = d.value.cpu.freqPerCore?.[i];
  return v > 0 ? v : null;
};
const freqScaleMhz = computed(
  () =>
    d.value.cpu.freqMaxMhz || Math.max(0, ...(d.value.cpu.freqPerCore || []).filter((v) => v > 0))
);
const freqBarStyle = (i) => {
  const f = coreFreqMhz(i);
  const scale = freqScaleMhz.value || 1;
  return { height: `${f ? Math.min(100, Math.max(6, (f / scale) * 100)) : 0}%` };
};
const freqLabel = (i) => {
  const f = coreFreqMhz(i);
  return f ? (Math.round(f / 10) / 100).toFixed(1) : '—';
};
const coreTip = (i, v) => {
  const parts = [t('线程 {n}', { n: i + 1 })];
  if (v != null) parts.push(`${Math.round(v)}%`);
  const f = coreFreqMhz(i);
  if (f) parts.push(`${(Math.round(f / 10) / 100).toFixed(2)} GHz`);
  return parts.join(' · ');
};
const freqRangeText = computed(() => {
  const vals = (d.value.cpu.freqPerCore || []).filter((v) => v > 0);
  if (!vals.length) return `${d.value.cpu.freqGHz} GHz`;
  const g = (v) => (Math.round(v / 10) / 100).toFixed(2);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  return lo === hi ? `${g(hi)} GHz` : `${g(lo)} – ${g(hi)} GHz`;
});

/** 网络/磁盘 spark：实时快照滚动缓冲（约 40 点），KB/s 口径 */
const netHistory = ref([]);
const dioHistory = ref([]);

/** GPU 曲线：实时快照滚动缓冲（约 60s 窗口），无快照前为空由图表空态兜底 */
const gpuHistory = ref([]);
const gpuLabels = computed(() => gpuHistory.value.map((p) => p.label));
const gpuSeries = computed(() => [
  {
    name: t('GPU 使用率'),
    color: chartColors.value.gpu,
    data: gpuHistory.value.map((p) => p.percent),
  },
]);
const gpuSparkData = computed(() => gpuHistory.value.map((p) => p.percent));
</script>

<template>
  <section>
    <u-page-header
      :title="t('总览')"
      :sub="t('系统 · 阵列 · 风扇 · 服务')"
      :tag="headerTag"
      :updated="lastUpdated"
    >
      <template #right>
        <label class="switch" :class="{ on: autoRefresh }" @click="autoRefresh = !autoRefresh">
          <span class="tr" />{{ t('自动') }}
        </label>
        <button
          class="btn sm"
          :title="t('生成状态分享图（PNG）')"
          :disabled="cardBusy"
          @click="genStatusCard"
        >
          <u-icon name="dl" />{{ t('状态卡') }}
        </button>
        <u-time-machine ref="timeMachine" />
      </template>
    </u-page-header>

    <!-- 第一行磁贴：CPU / 内存 / 网络吞吐 / 磁盘 IO -->
    <div class="grid">
      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div
            class="cap"
            style="display: flex; align-items: center; justify-content: space-between"
          >
            <span style="display: inline-flex; gap: 6px; align-items: center">
              <u-icon name="cpu" />{{ t('CPU 使用率') }}
            </span>
            <span class="cpuswitch">
              <span :class="{ on: cpuMode === 'usage' }" @click="cpuMode = 'usage'">
                {{ t('使用率') }}
              </span>
              <span :class="{ on: cpuMode === 'freq' }" @click="cpuMode = 'freq'">
                {{ t('频率') }}
              </span>
            </span>
          </div>
          <div class="big num">{{ d.cpu.percent }}<small>%</small></div>
          <div class="meter" style="margin-top: 9px">
            <i class="c-ok" :style="{ width: `${d.cpu.percent}%` }" />
          </div>
          <!-- ≥3 线程才显示柱条对比：1-2 线程整宽单柱形似进度条且无对比意义 -->
          <div
            v-if="(d.cpu.cores || []).length >= 3"
            class="cores"
            :style="{ gridTemplateColumns: `repeat(${coreCols}, 1fr)` }"
          >
            <span v-for="(v, i) in d.cpu.cores" :key="i" class="core" :title="coreTip(i, v)">
              <i :style="cpuMode === 'usage' ? { height: `${v}%` } : freqBarStyle(i)" />
              <em v-if="cpuMode === 'freq'" class="cf">{{ freqLabel(i) }}</em>
            </span>
          </div>
          <div class="mtxt">
            <span>{{ d.cpu.coresText }}</span>
            <span class="num">
              {{
                cpuMode === 'freq'
                  ? freqRangeText
                  : `${d.cpu.tempC ?? '—'} °C · ${d.cpu.freqGHz ?? '—'} GHz`
              }}
            </span>
          </div>
        </div>
      </div>

      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="server" />{{ t('内存') }}</div>
          <div class="big num">{{ d.mem.percent }}<small>%</small></div>
          <div class="meter" style="margin-top: 9px">
            <i class="c-info" :style="{ width: `${d.mem.percent}%` }" />
          </div>
          <div class="kv2" style="margin-top: 8px">
            <div class="kvrow kvline">
              <span class="muted small">{{ t('总大小') }}</span>
              <span class="small num">{{ d.mem.totalText }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">{{ t('已使用') }}</span>
              <span class="small num">{{ d.mem.usedText }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">{{ t('可用') }}</span>
              <span class="small num">{{ d.mem.availText }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">{{ t('缓冲') }}</span>
              <span class="small num">{{ d.mem.buffersText }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">{{ t('缓存') }}</span>
              <span class="small num">{{ d.mem.cachedText }}</span>
            </div>
            <div class="kvrow">
              <span class="muted small">{{ t('系统保留') }}</span>
              <span class="small num">{{ d.mem.reservedText }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="net" />{{ t('网络吞吐') }}</div>
          <div class="big num">
            {{ d.net.rxValue ?? d.net.rxText }}<small>{{ d.net.rxUnit ?? 'MB/s ↓' }}</small>
          </div>
          <div class="num" style="margin-top: 2px; font-size: 12px; color: var(--tx2)">
            {{ d.net.txText }}
          </div>
          <u-spark :data="netHistory" :color="chartColors.ok" />
        </div>
      </div>

      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="drive" />{{ t('磁盘 IO') }}</div>
          <div class="big num">
            {{ d.diskIo.readValue ?? d.diskIo.readText
            }}<small>{{ d.diskIo.readUnit ?? 'MB/s 读' }}</small>
          </div>
          <div class="num" style="margin-top: 2px; font-size: 12px; color: var(--tx2)">
            {{ d.diskIo.writeText }}
          </div>
          <u-spark :data="dioHistory" :color="chartColors.purp" />
        </div>
      </div>
    </div>

    <!-- 第二行磁贴：阵列 / GPU / 功耗 / 系统 -->
    <div class="grid">
      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="array" />{{ t('阵列') }}</div>
          <div class="big num">{{ d.array.total.split(' ')[0] }}<small>TB</small></div>
          <div class="meter" style="margin-top: 9px">
            <i class="c-ok" :style="{ width: `${d.array.usedPercent}%` }" />
          </div>
          <div class="mtxt">
            <span
              ><span class="st"><span class="dot" />{{ d.array.status }}</span></span
            >
            <span class="num">{{ d.array.usedText }}</span>
          </div>
          <div class="mtxt" style="margin-top: 2px">
            <span>{{ d.array.level }}</span>
            <span>{{ d.array.check }}</span>
          </div>
          <button
            class="btn sm"
            style="width: 100%; margin-top: 9px"
            @click="$router.push('/nasdeck/storage')"
          >
            {{ t('管理阵列') }}<u-icon name="chev" />
          </button>
        </div>
      </div>

      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="pulse" />{{ t('GPU 使用率') }}</div>
          <div class="big num">{{ d.gpu.percent }}<small>%</small></div>
          <u-spark :data="gpuSparkData" :color="chartColors.gpu" />
          <div class="mtxt">
            <span>{{ t('核显 · 温度') }} {{ d.gpu.tempC ?? '—' }} °C</span>
            <span class="num">{{ d.gpu.vramText }}</span>
          </div>
        </div>
      </div>

      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="power" />{{ t('整机功耗') }}</div>
          <div class="big num">{{ d.power.watts }}<small>W</small></div>
          <div class="meter" style="margin-top: 9px">
            <i :style="{ width: `${powerMeterPct}%` }" />
          </div>
          <div class="mtxt">
            <span
              >CPU <span class="num">{{ d.power.cpuW }} W</span></span
            >
            <span
              >DRAM <span class="num">{{ d.power.dramW }} W</span></span
            >
          </div>
        </div>
      </div>

      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="clock" />{{ t('系统') }}</div>
          <div class="big num">
            {{ d.system.uptimeDays ?? '—' }}<small>{{ d.system.uptimeRest ?? '天' }}</small>
          </div>
          <div class="kvrow kvline">
            <span class="muted small">{{ t('系统') }}</span>
            <span class="small num">{{ d.system.osVersion }}</span>
          </div>
          <div class="kvrow kvline">
            <span class="muted small">{{ t('负载 1/5/15m') }}</span>
            <span class="small num">{{ d.system.loadText }}</span>
          </div>
          <div class="kvrow">
            <span class="muted small">{{ t('进程数') }}</span>
            <span class="small num">{{ d.system.processCount }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- GPU 详细监控卡 -->
    <div class="wg">
      <div class="wg-h">
        <u-icon name="pulse" />
        <h3>{{ t('GPU 监控 · {n}', { n: d.gpuDetail.name }) }}</h3>
        <span class="x"
          ><span class="tag ok"><span class="dot" />{{ t('核显 · 正常') }}</span></span
        >
      </div>
      <div class="wg-b" style="display: flex; flex-wrap: wrap; gap: 22px">
        <div style="flex: 0 0 270px; min-width: 250px">
          <div class="num" style="font-size: 26px; font-weight: 700; line-height: 1.2">
            {{ d.gpuDetail.percent
            }}<span style="margin-left: 2px; font-size: 12.5px; font-weight: 500; color: var(--tx2)"
              >%</span
            >
          </div>
          <div class="meter" style="margin-top: 8px">
            <i :style="{ width: `${d.gpuDetail.percent}%`, background: 'var(--purp)' }" />
          </div>
          <div style="margin-top: 10px">
            <div class="kvrow kvline">
              <span class="muted small">{{ t('显存（共享）') }}</span
              ><span class="small num">{{ d.gpuDetail.vramText }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">{{ t('引擎占用') }}</span
              ><span class="small num">{{ d.gpuDetail.engineText }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">{{ t('GPU 频率') }}</span
              ><span class="small num">{{ d.gpuDetail.freqText }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">{{ t('温度') }}</span
              ><span class="small num t-ok">{{ d.gpuDetail.tempC }} °C</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">{{ t('功耗') }}</span
              ><span class="small num">{{ d.gpuDetail.watts }} W</span>
            </div>
            <div class="kvrow">
              <span class="muted small">{{ t('驱动 / 转码') }}</span
              ><span class="small">{{ d.gpuDetail.driverText }}</span>
            </div>
          </div>
        </div>
        <div style="flex: 1; min-width: 280px">
          <u-line-chart
            :series="gpuSeries"
            :labels="gpuLabels"
            :height="196"
            :tip-fmt="(v) => `${v.toFixed(0)}%`"
            :y-tick-fmt="(v) => `${v}%`"
          />
          <div class="legend">
            <span><i :style="{ background: chartColors.gpu }" />{{ t('GPU 使用率') }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 风扇转速 / Docker -->
    <div class="grid">
      <div class="wg t6">
        <div class="wg-h">
          <u-icon name="fan" />
          <h3>{{ t('风扇转速') }}</h3>
          <span class="x"
            ><span class="tag" :class="d.fans.length ? 'acc' : 'mute'"
              ><span class="dot" />{{
                d.fans.length
                  ? t('接管中 · {a}/{b} 运转', { a: d.fans.length, b: d.fans.length })
                  : t('未配置')
              }}</span
            ></span
          >
        </div>
        <div class="wg-b">
          <div v-if="d.fans.length" class="fans3">
            <div v-for="fan in d.fans" :key="fan.name" class="fanb">
              <div class="fn">
                <fan-rotor :rpm="fan.rpm > 0 ? fan.rpm : Math.round(fan.dutyPercent * 26.5)" />
                {{ fan.name }}
                <span class="chip">{{ fan.chip }}</span>
              </div>
              <div class="fr">
                <b class="num">{{ fan.rpm }}</b
                ><small> RPM</small>
              </div>
              <div class="meter thin"><i :style="{ width: `${fan.dutyPercent}%` }" /></div>
              <div class="fd">
                <span>{{ t('占空比 {d}%', { d: fan.dutyPercent }) }}</span>
                <span>{{ fan.tempC }} °C</span>
              </div>
            </div>
          </div>
          <div v-else class="small muted" style="padding: 18px 0; text-align: center">
            {{ t('风扇未配置 · 到「风扇」页添加风区并接管后此处显示实时转速') }}
          </div>
          <button
            class="btn sm"
            style="width: 100%; margin-top: 11px"
            @click="$router.push('/nasdeck/fan')"
          >
            {{ t('风扇控制与曲线编辑') }}<u-icon name="chev" />
          </button>
        </div>
      </div>

      <div class="wg t6">
        <div class="wg-h">
          <u-icon name="docker" />
          <h3>Docker</h3>
          <span class="x"
            ><span class="st"><span class="dot" />{{ d.dockerText ?? '—' }}</span></span
          >
        </div>
        <div class="wg-b" style="padding-top: 8px">
          <div v-if="d.dockerBrief.length" class="kv2">
            <template v-for="c in d.dockerBrief" :key="c.name">
              <div class="kvrow kvline">
                <span :class="{ muted: c.exited }">{{ c.name }}</span>
                <span v-if="!c.exited" class="num small">{{ c.statText }}</span>
                <span v-else class="st bad small"><span class="dot" />{{ t('已退出') }}</span>
              </div>
            </template>
          </div>
          <div v-else class="small muted" style="padding: 8px 0 2px">
            {{ d.dockerText ?? t('未检测到 Docker 容器') }}
          </div>
          <button
            class="btn sm"
            style="width: 100%; margin-top: 11px"
            @click="$router.push('/nasdeck/docker')"
          >
            {{ t('查看容器') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 硬盘温度 / 缓存与备份 -->
    <div class="grid">
      <div class="wg t8">
        <div class="wg-h">
          <u-icon name="drive" />
          <h3>{{ t('硬盘温度') }}</h3>
          <span class="x">{{
            d.diskTemps.length
              ? t('{n} 盘 · 按阈值着色', { n: d.diskTemps.length })
              : t('无温度数据源')
          }}</span>
        </div>
        <div class="wg-b">
          <div v-if="d.diskTemps.length" class="temps">
            <div v-for="t in d.diskTemps" :key="t.label" class="temp" :class="tempClass(t.tempC)">
              <div class="n">{{ t.label }}</div>
              <div class="v num">{{ t.tempC }} °C</div>
            </div>
          </div>
          <div v-else class="small muted" style="padding: 18px 0; text-align: center">
            {{ t('未检测到硬盘温度传感器 · 传感器接入后此处显示各盘温度') }}
          </div>
          <div class="legend">
            <span><i style="background: var(--sf3)" />&lt; 40 {{ t('正常') }}</span>
            <span
              ><i style="background: var(--warnbg); border: 1px solid var(--warn)" />40 – 50
              {{ t('偏高') }}</span
            >
            <span
              ><i style="background: var(--badbg); border: 1px solid var(--bad)" />&gt; 50
              {{ t('过热') }}</span
            >
          </div>
        </div>
      </div>

      <div class="wg t4">
        <div class="wg-h">
          <u-icon name="cloud" />
          <h3>{{ t('存储卷概览') }}</h3>
          <span class="x"
            ><span class="st"><span class="dot" />{{ d.storageSummary ?? '—' }}</span></span
          >
        </div>
        <div class="wg-b">
          <div
            style="
              display: flex;
              justify-content: space-between;
              margin-bottom: 6px;
              font-size: 12px;
              color: var(--tx2);
            "
          >
            <span>{{ d.cache.label }}</span
            ><span class="num">{{ d.cache.percent }}%</span>
          </div>
          <div class="meter thin">
            <i class="c-info" :style="{ width: `${d.cache.percent}%` }" />
          </div>
          <div class="mtxt">
            <span class="num">{{ d.cache.usedText }}</span
            ><span>{{ d.cache.tempC }}</span>
          </div>
          <div style="height: 1px; margin: 11px 0; background: var(--bd)" />
          <div
            style="
              display: flex;
              justify-content: space-between;
              margin-bottom: 6px;
              font-size: 12px;
              color: var(--tx2);
            "
          >
            <span>{{ d.cloud.label }}</span
            ><span class="num">{{ d.cloud.percent }}%</span>
          </div>
          <div class="meter thin"><i class="c-ok" :style="{ width: `${d.cloud.percent}%` }" /></div>
          <div class="mtxt">
            <span class="num">{{ d.cloud.usedText }}</span
            ><span>{{ d.cloud.syncText }}</span>
          </div>
          <button
            class="btn sm"
            style="width: 100%; margin-top: 11px"
            @click="$router.push('/nasdeck/storage')"
          >
            {{ t('查看存储卷') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 活动告警 -->
    <div class="wg">
      <div class="wg-h">
        <u-icon name="shield" />
        <h3>{{ t('活动告警') }}</h3>
        <span class="x"
          ><span class="tag warn"><span class="dot" />{{ alerts.length }} {{ t('条') }}</span></span
        >
      </div>
      <div class="wg-b">
        <div
          v-for="(a, i) in alerts"
          :key="i"
          class="alertrow"
          :style="i === alerts.length - 1 ? 'margin-bottom: 0' : ''"
        >
          <span class="lvl warn">WARN</span>
          <span class="txt">{{ a.text }}</span>
          <span class="tm num">{{ a.time }}</span>
          <button class="btn sm" @click="$router.push(a.jump.path)">{{ a.jump.action }}</button>
        </div>
        <div v-if="!alerts.length" class="small muted" style="padding: 6px 0">
          {{ live ? t('当前无活动告警') : t('后端不可达，显示演示告警') }}
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 柱条区固定总高、行数均分：单行（≤6 线程）柱条自动加高填满、双行与原 36px
   相当——磁贴总高恒定，底部不再随行数留空；仅本视图生效 */
.cores {
  grid-auto-rows: 1fr;
  height: 78px;
}

.cores .core {
  height: auto;
}

/* 使用率/频率 双视图切换（视图内局部控件，不入全局设计令牌） */
.cpuswitch {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--bd);
  border-radius: 4px;
}

.cpuswitch span {
  padding: 1px 8px;
  font-size: 11px;
  color: var(--tx2);
  cursor: pointer;
  user-select: none;
}

.cpuswitch span.on {
  color: #fff;
  background: var(--acc);
}

/* 频率视图：柱内顶部标 GHz 数值 */
.core .cf {
  position: absolute;
  top: 1px;
  right: 0;
  left: 0;
  font-size: 8.5px;
  font-style: normal;
  line-height: 1.1;
  color: var(--tx2);
  text-align: center;
}
</style>
