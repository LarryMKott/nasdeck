<script setup>
/** 总览：UNRAID Dashboard 式磁贴 + GPU 监控 + 风扇/Docker/温度/缓存/告警（后端实时 + 演示回退） */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { colors, dashboard as mockDashboard, activeAlerts as mockAlerts } from '../mock';
import { walk, timeLabels } from '../utils/series';
import { tempClass } from '../utils/format';
import { useViewData } from '../composables/useViewData';
import { useRealtimeStore } from '../stores/realtime';
import * as nasData from '../api/data';
import UPageHeader from '../components/UPageHeader.vue';
import USpark from '../components/USpark.vue';
import ULineChart from '../components/ULineChart.vue';
import FanRotor from '../components/FanRotor.vue';

defineOptions({ name: 'NasDash' });

const { data: d, live } = useViewData(nasData.fetchDashboard, mockDashboard);
const { data: alerts } = useViewData(nasData.fetchActiveAlerts, mockAlerts);

/** WS 实时快照合并（仅更新磁贴数字，图表/序列仍走加载时数据） */
const realtime = useRealtimeStore();
onMounted(() => realtime.acquire());
onBeforeUnmount(() => realtime.release());
watch(
  () => realtime.snapshot,
  (snap) => {
    if (!snap || !live.value) return;
    d.value.cpu.percent = Math.round(snap.cpu_percent * 10) / 10;
    nasData.applyCpuRealtime(d.value.cpu, snap);
    d.value.mem.percent = snap.mem_percent;
    const ifaces = Object.entries(snap.net);
    d.value.net.rxText = `${(ifaces.reduce((a, [, v]) => a + v.rx_kbps, 0) / 1024).toFixed(1)} MB/s ↓`;
    d.value.diskIo.readText = `${((snap.disk_io.read_kbps ?? 0) / 1024).toFixed(0)} MB/s 读`;
  }
);

const headerTag = computed(() => ({
  type: live.value ? 'ok' : 'acc',
  text: live.value ? '正常' : '演示数据',
}));
const autoRefresh = ref(true);

/** CPU 磁贴：每线程 使用率/频率 双视图（WS 1s 快照驱动） */
const cpuMode = ref('usage');
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
  const parts = [`线程 ${i + 1}`];
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

/** spark 序列（种子与原型一致，形态稳定；联调阶段占位） */
const sparks = {
  net: walk(40, 7, 12, 4, 7.2, 19.2),
  dio: walk(40, 11, 86, 26, 51.6, 137.6),
  gpu: walk(40, 12, 15, 8, 9, 24),
};

const gpuLabels = timeLabels(60, 1);
const gpuSeries = [
  { name: 'GPU 使用率', color: colors.gpu, data: walk(60, 13, 15, 8, 2, 60) },
  { name: '显存占用', color: colors.info, data: walk(60, 14, 53, 5, 40, 72), dash: true },
];
</script>

<template>
  <section>
    <u-page-header title="总览" sub="系统 · 阵列 · 风扇 · 服务" :tag="headerTag" updated="10:32:12">
      <template #right>
        <label class="switch" :class="{ on: autoRefresh }" @click="autoRefresh = !autoRefresh">
          <span class="tr" />自动
        </label>
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
              <u-icon name="cpu" />CPU 使用率
            </span>
            <span class="cpuswitch">
              <span :class="{ on: cpuMode === 'usage' }" @click="cpuMode = 'usage'">使用率</span>
              <span :class="{ on: cpuMode === 'freq' }" @click="cpuMode = 'freq'">频率</span>
            </span>
          </div>
          <div class="big num">{{ d.cpu.percent }}<small>%</small></div>
          <div class="meter" style="margin-top: 9px">
            <i class="c-ok" :style="{ width: `${d.cpu.percent}%` }" />
          </div>
          <div class="cores">
            <span v-for="(v, i) in d.cpu.cores" :key="i" class="core" :title="coreTip(i, v)">
              <i :style="cpuMode === 'usage' ? { height: `${v}%` } : freqBarStyle(i)" />
              <em v-if="cpuMode === 'freq'" class="cf">{{ freqLabel(i) }}</em>
            </span>
          </div>
          <div class="mtxt">
            <span>{{ d.cpu.coresText }}</span>
            <span class="num">
              {{ cpuMode === 'freq' ? freqRangeText : `${d.cpu.tempC} °C · ${d.cpu.freqGHz} GHz` }}
            </span>
          </div>
        </div>
      </div>

      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="server" />内存</div>
          <div class="big num">{{ d.mem.percent }}<small>%</small></div>
          <div class="meter" style="margin-top: 9px">
            <i class="c-info" :style="{ width: `${d.mem.percent}%` }" />
          </div>
          <div class="mtxt">
            <span>{{ d.mem.usedText }}</span>
            <span class="num">{{ d.mem.totalText }}</span>
          </div>
        </div>
      </div>

      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="net" />网络吞吐</div>
          <div class="big num">{{ d.net.rxText.split(' ')[0] }}<small>MB/s ↓</small></div>
          <div class="num" style="margin-top: 2px; font-size: 12px; color: var(--tx2)">
            {{ d.net.txText }}
          </div>
          <u-spark :data="sparks.net" :color="colors.ok" />
        </div>
      </div>

      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="drive" />磁盘 IO</div>
          <div class="big num">{{ d.diskIo.readText.split(' ')[0] }}<small>MB/s 读</small></div>
          <div class="num" style="margin-top: 2px; font-size: 12px; color: var(--tx2)">
            {{ d.diskIo.writeText }}
          </div>
          <u-spark :data="sparks.dio" :color="colors.purp" />
        </div>
      </div>
    </div>

    <!-- 第二行磁贴：阵列 / GPU / 功耗 / 系统 -->
    <div class="grid">
      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="array" />阵列</div>
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
            管理阵列<u-icon name="chev" />
          </button>
        </div>
      </div>

      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="pulse" />GPU 使用率</div>
          <div class="big num">{{ d.gpu.percent }}<small>%</small></div>
          <u-spark :data="sparks.gpu" :color="colors.gpu" />
          <div class="mtxt">
            <span>核显 · 温度 {{ d.gpu.tempC }} °C</span>
            <span class="num">{{ d.gpu.vramText }}</span>
          </div>
        </div>
      </div>

      <div class="wg tile-wg t3">
        <div class="wg-b">
          <div class="cap"><u-icon name="power" />整机功耗</div>
          <div class="big num">{{ d.power.watts }}<small>W</small></div>
          <div class="meter" style="margin-top: 9px"><i :style="{ width: '62%' }" /></div>
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
          <div class="cap"><u-icon name="clock" />系统</div>
          <div class="big num">
            23<small>{{ d.system.uptime.slice(2) }}</small>
          </div>
          <div class="kvrow kvline">
            <span class="muted small">系统</span>
            <span class="small num">{{ d.system.osVersion }}</span>
          </div>
          <div class="kvrow kvline">
            <span class="muted small">负载 1/5/15m</span>
            <span class="small num">{{ d.system.loadText }}</span>
          </div>
          <div class="kvrow">
            <span class="muted small">进程数</span>
            <span class="small num">{{ d.system.processCount }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- GPU 详细监控卡 -->
    <div class="wg">
      <div class="wg-h">
        <u-icon name="pulse" />
        <h3>GPU 监控 · {{ d.gpuDetail.name }}</h3>
        <span class="x"
          ><span class="tag ok"><span class="dot" />核显 · 正常</span></span
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
              <span class="muted small">显存（共享）</span
              ><span class="small num">{{ d.gpuDetail.vramText }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">引擎占用</span
              ><span class="small num">{{ d.gpuDetail.engineText }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">GPU 频率</span
              ><span class="small num">{{ d.gpuDetail.freqText }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">温度</span
              ><span class="small num t-ok">{{ d.gpuDetail.tempC }} °C</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">功耗</span
              ><span class="small num">{{ d.gpuDetail.watts }} W</span>
            </div>
            <div class="kvrow">
              <span class="muted small">驱动 / 转码</span
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
            <span><i :style="{ background: colors.gpu }" />GPU 使用率</span>
            <span><i :style="{ background: colors.info }" />显存占用</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 风扇转速 / Docker -->
    <div class="grid">
      <div class="wg t6">
        <div class="wg-h">
          <u-icon name="fan" />
          <h3>风扇转速</h3>
          <span class="x"
            ><span class="tag acc"><span class="dot" />接管中 · 3/3 运转</span></span
          >
        </div>
        <div class="wg-b">
          <div class="fans3">
            <div v-for="fan in d.fans" :key="fan.name" class="fanb">
              <div class="fn">
                <fan-rotor :dur-sec="fan.durSec" />
                {{ fan.name }}
                <span class="chip">{{ fan.chip }}</span>
              </div>
              <div class="fr">
                <b class="num">{{ fan.rpm }}</b
                ><small> RPM</small>
              </div>
              <div class="meter thin"><i :style="{ width: `${fan.dutyPercent}%` }" /></div>
              <div class="fd">
                <span>占空比 {{ fan.dutyPercent }}%</span>
                <span>{{ fan.tempC }} °C</span>
              </div>
            </div>
          </div>
          <button
            class="btn sm"
            style="width: 100%; margin-top: 11px"
            @click="$router.push('/nasdeck/fan')"
          >
            风扇控制与曲线编辑<u-icon name="chev" />
          </button>
        </div>
      </div>

      <div class="wg t6">
        <div class="wg-h">
          <u-icon name="docker" />
          <h3>Docker</h3>
          <span class="x"
            ><span class="st"><span class="dot" />3 运行中 · 1 退出</span></span
          >
        </div>
        <div class="wg-b" style="padding-top: 8px">
          <div class="kv2">
            <template v-for="c in d.dockerBrief" :key="c.name">
              <div class="kvrow kvline">
                <span :class="{ muted: c.exited }">{{ c.name }}</span>
                <span v-if="!c.exited" class="num small">{{ c.statText }}</span>
                <span v-else class="st bad small"><span class="dot" />已退出</span>
              </div>
            </template>
          </div>
          <button
            class="btn sm"
            style="width: 100%; margin-top: 11px"
            @click="$router.push('/nasdeck/docker')"
          >
            查看容器
          </button>
        </div>
      </div>
    </div>

    <!-- 硬盘温度 / 缓存与备份 -->
    <div class="grid">
      <div class="wg t8">
        <div class="wg-h">
          <u-icon name="drive" />
          <h3>硬盘温度</h3>
          <span class="x">6 盘位 · 按阈值着色</span>
        </div>
        <div class="wg-b">
          <div class="temps">
            <div v-for="t in d.diskTemps" :key="t.label" class="temp" :class="tempClass(t.tempC)">
              <div class="n">{{ t.label }}</div>
              <div class="v num">{{ t.tempC }} °C</div>
            </div>
          </div>
          <div class="legend">
            <span><i style="background: var(--sf3)" />&lt; 40 正常</span>
            <span
              ><i style="background: var(--warnbg); border: 1px solid var(--warn)" />40 – 50
              偏高</span
            >
            <span
              ><i style="background: var(--badbg); border: 1px solid var(--bad)" />&gt; 50
              过热</span
            >
          </div>
        </div>
      </div>

      <div class="wg t4">
        <div class="wg-h">
          <u-icon name="cloud" />
          <h3>缓存与备份</h3>
          <span class="x"
            ><span class="st"><span class="dot" />已连接</span></span
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
            ><span>{{ d.cache.tempC }} °C</span>
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
            查看存储卷
          </button>
        </div>
      </div>
    </div>

    <!-- 活动告警 -->
    <div class="wg">
      <div class="wg-h">
        <u-icon name="shield" />
        <h3>活动告警</h3>
        <span class="x"
          ><span class="tag warn"><span class="dot" />{{ alerts.length }} 条</span></span
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
      </div>
    </div>
  </section>
</template>

<style scoped>
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
