<script setup>
/** 大屏轮播模式（花活 A）：全屏监控墙——时钟 + 四屏轮播（总览/硬盘/温度/事件）。
 * 独立路由不套 UnraidLayout（无顶栏）；自带深色配色（无 .nd 主题变量）。
 * Esc / 点击呼出退出按钮；轮播间隔 ?sec= 可调（5-60，默认 10）。数据 5s 轮询。
 * 星舰 HUD（花活二期 P）：底部荧光波形带（scopeCore 内核，rAF 平滑滚动，页面隐藏
 * 自动停）+ 径向擦除转场 + firing 告警全屏红光呼吸 + 按宿主主题切换 accent。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAppStore } from '@/stores/modules/app';
import { fetchKiosk } from '../services/monitor';
import UChassis3D from '../components/UChassis3D.vue';
import { drawGlowChannel } from '../utils/scopeCore';

defineOptions({ name: 'NasKiosk' });

const router = useRouter();
const appStore = useAppStore();

/** 主题 accent 自动适配（花活二期 P）：大屏保持深色底，仅换强调色 */
const ACCENTS = {
  dark: '#f15a2c',
  cyber: '#2ee6c8',
  terminal: '#41d98d',
  light: '#f15a2c',
};
const accent = computed(() => ACCENTS[appStore.resolvedTheme] || ACCENTS.dark);

/** 轮播间隔（秒）：?sec= 钳制 5-60 */
const intervalSec = computed(() => {
  const n = parseInt(new URLSearchParams(location.search).get('sec') || '10', 10);
  return Number.isFinite(n) ? Math.min(60, Math.max(5, n)) : 10;
});

const d = ref({ realtime: null, temps: null, disks: null, events: null, fans: [] });
const screenIdx = ref(0);
const now = ref(new Date());
const showExit = ref(false);
const paused = ref(false);

const SCREENS = ['总览', '硬盘', '温度', '事件']; // 渲染处经 t() 包裹
const HEALTH_COLOR = {
  passed: '#3fb68b',
  warning: '#eca43c',
  failing: '#e5484d',
  unknown: '#5b5d65',
};
const HEALTH_TEXT = { passed: '正常', warning: '警告', failing: '故障', unknown: '未知' };

let pollTimer = null;
let rotateTimer = null;
let clockTimer = null;
let hideExitTimer = null;

async function poll() {
  const r = await fetchKiosk();
  d.value = r.data;
  // 波形带点缓冲：每次轮询推进一格（CPU% + 全网口收发合计 KB/s）
  const rt = r.data.realtime;
  if (rt) {
    const net = Object.values(rt.net || {}).reduce(
      (s, v) => s + (v.rx_kbps || 0) + (v.tx_kbps || 0),
      0
    );
    bandPoints.value.push({ t: Date.now(), v: { cpu: rt.cpu_percent ?? null, net } });
    const cutoff = Date.now() - BAND_WINDOW_MS - 10000;
    while (bandPoints.value.length && bandPoints.value[0].t < cutoff) bandPoints.value.shift();
  }
  watchAlertFiring();
}

// ---- 星舰 HUD：底部荧光波形带（scopeCore 内核 + rAF 平滑滚动，隐藏页签自动停） ----
const BAND_WINDOW_MS = 5 * 60 * 1000;
const bandPoints = ref([]);
const bandCanvas = ref(null);
let bandRaf = 0;

function drawBand() {
  bandRaf = requestAnimationFrame(drawBand);
  const canvas = bandCanvas.value;
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (!w || !h) return;
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const tNow = Date.now();
  const t0 = tNow - BAND_WINDOW_MS;
  const data = bandPoints.value;
  if (!data.length) return;
  drawGlowChannel(ctx, data, 'net', '#3fb68b', {
    w,
    h,
    t0,
    tNow,
    padTop: 8,
    lineWidth: 1.3,
    glow: 4,
  });
  drawGlowChannel(ctx, data, 'cpu', accent.value, { w, h, t0, tNow, padTop: 8 });
}

// ---- firing 告警红光：事件屏已有数据，firing 出现/消失驱动全屏边缘呼吸 ----
const alertFiring = ref(false);
let lastFiringKey = '';

function watchAlertFiring() {
  const events = d.value.events || [];
  const key = events
    .filter((e) => e.status === 'firing')
    .map((e) => e.id)
    .join(',');
  if (key !== lastFiringKey) {
    lastFiringKey = key;
    alertFiring.value = !!key;
  }
}

function rotate() {
  if (!paused.value) screenIdx.value = (screenIdx.value + 1) % SCREENS.length;
}

function wakeUi() {
  showExit.value = true;
  clearTimeout(hideExitTimer);
  hideExitTimer = setTimeout(() => (showExit.value = false), 2600);
}

function onKeydown(e) {
  if (e.key === 'Escape') router.push('/nasdeck/dash');
}

const clockText = computed(() =>
  now.value.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
);
const dateText = computed(() =>
  now.value.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })
);

/** 总览屏大数字（realtime 缓存缺项显示 —） */
const rt = computed(() => d.value.realtime || {});
const topTemps = computed(() =>
  [...(d.value.temps || [])].sort((a, b) => (b.celsius ?? -99) - (a.celsius ?? -99)).slice(0, 8)
);

onMounted(() => {
  poll();
  pollTimer = setInterval(poll, 5000);
  rotateTimer = setInterval(rotate, intervalSec.value * 1000);
  clockTimer = setInterval(() => (now.value = new Date()), 1000);
  window.addEventListener('keydown', onKeydown);
  document.documentElement.style.background = '#05060a';
  drawBand();
});

onBeforeUnmount(() => {
  clearInterval(pollTimer);
  clearInterval(rotateTimer);
  clearInterval(clockTimer);
  cancelAnimationFrame(bandRaf);
  bandRaf = 0;
  window.removeEventListener('keydown', onKeydown);
  document.documentElement.style.background = '';
});
</script>

<template>
  <div class="kiosk" @mousemove="wakeUi" @click="wakeUi">
    <!-- firing 告警全屏红光呼吸（花活二期 P） -->
    <div v-if="alertFiring" class="k-alert-glow" />
    <header class="k-head">
      <div class="k-clock num" :style="{ color: accent }">{{ clockText }}</div>
      <div class="k-brand">
        <span class="k-logo" :style="{ color: accent }">nasdeck</span>
        <span class="k-date">{{ dateText }}</span>
      </div>
    </header>

    <main class="k-stage">
      <transition name="kfade" mode="out-in">
        <!-- 屏 1：总览 -->
        <section v-if="screenIdx === 0" key="ov" class="k-screen">
          <div class="k-grid">
            <div class="k-card">
              <span class="k-label">CPU</span>
              <span class="k-big num"
                >{{ rt.cpu_percent != null ? rt.cpu_percent : '—' }}<i>%</i></span
              >
            </div>
            <div class="k-card">
              <span class="k-label">{{ t('内存') }}</span>
              <span class="k-big num"
                >{{ rt.mem_percent != null ? rt.mem_percent : '—' }}<i>%</i></span
              >
            </div>
            <div class="k-card">
              <span class="k-label">{{ t('网速 ↓') }}</span>
              <span class="k-big num"
                >{{
                  rt.net
                    ? Object.values(rt.net)
                        .reduce((s, v) => s + (v.rx_kbps || 0), 0)
                        .toFixed(0)
                    : '—'
                }}<i>KB/s</i></span
              >
            </div>
            <div class="k-card">
              <span class="k-label">{{ t('网速 ↑') }}</span>
              <span class="k-big num"
                >{{
                  rt.net
                    ? Object.values(rt.net)
                        .reduce((s, v) => s + (v.tx_kbps || 0), 0)
                        .toFixed(0)
                    : '—'
                }}<i>KB/s</i></span
              >
            </div>
          </div>
          <div class="k-foot">
            <span>{{ t('负载') }} {{ (rt.load || []).join(' / ') || '—' }}</span>
            <span>{{ t('进程') }} {{ rt.process_count ?? '—' }}</span>
            <span>{{ t('运行') }} {{ Math.floor((rt.uptime_s || 0) / 86400) }} {{ t('天') }}</span>
          </div>
        </section>

        <!-- 屏 2：硬盘 -->
        <section v-else-if="screenIdx === 1" key="dk" class="k-screen">
          <div v-if="d.disks?.length" class="k-rows">
            <div v-for="(disk, i) in d.disks.slice(0, 8)" :key="i" class="k-row">
              <span
                class="k-dot"
                :style="{ background: HEALTH_COLOR[disk.health] || HEALTH_COLOR.unknown }"
              />
              <span class="k-name">{{ disk.device }}</span>
              <span class="k-sub">{{ disk.size_human }}</span>
              <span v-if="disk.temp_c != null" class="k-sub num"
                >{{ Math.round(disk.temp_c) }} °C</span
              >
              <span class="k-tag" :style="{ color: HEALTH_COLOR[disk.health] }">
                {{ HEALTH_TEXT[disk.health] || disk.health }}
              </span>
              <!-- 健康分（花活二期 J 收口）：oracle 评分随 /storage/disks 下发 -->
              <span
                v-if="disk.oracle?.score != null"
                class="k-tag num"
                :style="{
                  color:
                    disk.oracle.score >= 85
                      ? '#3fb68b'
                      : disk.oracle.score >= 60
                        ? '#eca43c'
                        : '#e5484d',
                }"
                :title="t('健康分')"
              >
                {{ disk.oracle.score }}
              </span>
            </div>
          </div>
          <div v-else class="k-empty">{{ t('磁盘清单不可用') }}</div>
        </section>

        <!-- 屏 3：温度（右半立体机箱，三期 R3；内联变量桥接 kiosk 固定深色调色板） -->
        <section v-else-if="screenIdx === 2" key="tp" class="k-screen k-tp">
          <div v-if="topTemps.length" class="k-rows">
            <div v-for="(t, i) in topTemps" :key="i" class="k-row">
              <span class="k-name">{{ t.label || t.chip }}</span>
              <div class="k-bar">
                <i
                  :style="{
                    width: `${Math.min(100, ((t.celsius ?? 0) / 100) * 100)}%`,
                    background:
                      (t.celsius ?? 0) >= 60
                        ? '#e5484d'
                        : (t.celsius ?? 0) >= 45
                          ? '#eca43c'
                          : '#3fb68b',
                  }"
                />
              </div>
              <span class="k-tag num">{{ t.celsius != null ? `${t.celsius} °C` : '—' }}</span>
            </div>
          </div>
          <div v-else class="k-empty">{{ t('温度传感器不可用') }}</div>
          <div
            class="k-iso"
            :style="{
              '--sf2': '#17181c',
              '--sf3': '#101116',
              '--bd': '#26282f',
              '--acc': accent,
              '--ok': '#3fb68b',
              '--warn': '#eca43c',
              '--bad': '#e5484d',
              '--info': '#4c8bf5',
              '--purp': '#a78bfa',
              '--tx0': '#e8ecf4',
              '--tx2': '#8b8d95',
              '--tx3': '#5b5d65',
            }"
          >
            <u-chassis3-d
              :sensors="d.temps ?? []"
              :fans="d.fans ?? []"
              :disks="
                (d.disks ?? []).map((dk, i) => ({
                  device: dk.device,
                  model: dk.model || dk.device,
                  capacity: dk.size_human,
                  tempC: dk.temp_c != null ? Math.round(dk.temp_c) : null,
                }))
              "
              :io="rt.disk_io_devices ?? null"
              :net="rt.net ?? null"
              :power="rt.power ?? null"
              :gpu-available="!!rt.gpu?.available"
              template="compact"
              preset="high"
            />
          </div>
        </section>

        <!-- 屏 4：事件 -->
        <section v-else key="ev" class="k-screen">
          <div v-if="d.events?.length" class="k-rows">
            <div v-for="e in d.events" :key="e.id" class="k-row">
              <span
                class="k-dot"
                :style="{ background: e.status === 'firing' ? '#e5484d' : '#3fb68b' }"
              />
              <span class="k-sub num">{{ (e.fired_at || '').slice(5, 16) }}</span>
              <span class="k-name">{{ e.rule_name }}</span>
              <span class="k-sub">{{ e.message }}</span>
            </div>
          </div>
          <div v-else class="k-empty">{{ t('暂无事件（—）') }}</div>
        </section>
      </transition>
    </main>

    <!-- 荧光波形带（花活二期 P）：CPU + 全网口吞吐，5 分钟窗，rAF 平滑滚动 -->
    <div class="k-band-wrap">
      <canvas ref="bandCanvas" class="k-band" />
      <span class="k-band-tag num" :style="{ color: accent }">CPU</span>
      <span class="k-band-tag net num">NET</span>
    </div>

    <footer class="k-footbar">
      <div class="k-dots">
        <span
          v-for="(name, i) in SCREENS"
          :key="name"
          class="k-dot-i"
          :class="{ on: screenIdx === i }"
          :style="screenIdx === i ? { background: accent } : {}"
          :title="t(name)"
        />
      </div>
      <button class="k-exit" :class="{ show: showExit }" @click="router.push('/nasdeck/dash')">
        {{ t('退出大屏（Esc）') }}
      </button>
      <span class="k-hint" :class="{ show: showExit }">{{
        paused ? t('已暂停') : `${intervalSec}s / ${t('屏')}`
      }}</span>
    </footer>
  </div>
</template>

<style scoped>
.kiosk {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  padding: 28px 40px 20px;
  font-family:
    Inter,
    -apple-system,
    'Segoe UI',
    'Microsoft YaHei',
    sans-serif;
  color: #e8ecf4;
  background: radial-gradient(1100px 500px at 75% -10%, rgb(241 90 44 / 7%), transparent), #05060a;
}

.k-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.k-clock {
  font-size: 64px;
  font-weight: 200;
  font-variant-numeric: tabular-nums;
  color: #f15a2c;
  letter-spacing: 0.04em;
}

.k-brand {
  display: flex;
  gap: 14px;
  align-items: baseline;
}

.k-logo {
  font-size: 20px;
  font-weight: 800;
  color: #f15a2c;
}

.k-date {
  font-size: 14px;
  color: #8b8d95;
}

.k-stage {
  display: flex;
  flex: 1;
  align-items: center;
  min-height: 0;
}

/* 4K 适配：背景保持全幅出血，内容三段限宽居中——卡片不至拉成超宽扁条；
   ≥2560 视口（4K 150%/2K 100%）按大屏语义放大字号，远距离可读 */
.k-head,
.k-screen,
.k-footbar {
  width: 100%;
  max-width: 2560px;
  margin-right: auto;
  margin-left: auto;
}

@media (width >= 2560px) {
  .kiosk {
    padding: 40px 56px 28px;
  }

  .k-clock {
    font-size: 88px;
  }

  .k-grid {
    gap: 28px;
  }

  .k-card {
    gap: 12px;
    padding: 36px 40px;
  }

  .k-label {
    font-size: 19px;
  }

  .k-big {
    font-size: 80px;
  }

  .k-big i {
    font-size: 26px;
  }

  .k-foot {
    gap: 44px;
    margin-top: 40px;
    font-size: 19px;
  }

  .k-rows {
    gap: 18px;
  }

  .k-row {
    gap: 22px;
    padding: 18px 26px;
  }

  .k-name {
    min-width: 260px;
    font-size: 23px;
  }

  .k-sub,
  .k-tag {
    font-size: 19px;
  }

  .k-bar {
    height: 12px;
  }

  .k-empty {
    font-size: 20px;
  }
}

.k-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 22px;
}

.k-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 26px 28px;
  background: #0d0f14;
  border: 1px solid #1c1e26;
  border-radius: 14px;
}

.k-label {
  font-size: 14px;
  color: #8b8d95;
  letter-spacing: 0.1em;
}

.k-big {
  font-size: 56px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.k-big i {
  margin-left: 6px;
  font-size: 18px;
  font-style: normal;
  font-weight: 400;
  color: #8b8d95;
}

.k-foot {
  display: flex;
  gap: 34px;
  margin-top: 30px;
  font-size: 14px;
  color: #8b8d95;
}

.k-rows {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
}

.k-row {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 12px 18px;
  background: #0d0f14;
  border: 1px solid #1c1e26;
  border-radius: 10px;
}

.k-dot {
  flex: none;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.k-name {
  min-width: 180px;
  font-size: 17px;
  font-weight: 600;
}

.k-sub {
  flex: 1;
  overflow: hidden;
  font-size: 14px;
  color: #8b8d95;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.k-tag {
  font-size: 14px;
  font-weight: 700;
}

.k-bar {
  flex: 1;
  height: 8px;
  background: #14161c;
  border-radius: 4px;

  i {
    display: block;
    height: 100%;
    border-radius: 4px;
    transition: width 400ms ease;
  }
}

.k-empty {
  padding: 40px;
  font-size: 15px;
  color: #5b5d65;
  text-align: center;
}

/* 温度屏：左读数右立体机箱（三期 R3 Kiosk 挂载） */
.k-tp {
  display: flex;
  gap: 28px;
  align-items: center;

  > .k-rows {
    flex: 1;
    min-width: 0;
  }

  .k-iso {
    flex: 0 0 44%;
    min-width: 0;

    svg {
      height: 360px;
    }
  }
}

/* 星舰 HUD（花活二期 P）：firing 告警红光呼吸（全屏边缘） */
.k-alert-glow {
  position: fixed;
  inset: 0;
  z-index: 5;
  pointer-events: none;
  box-shadow: inset 0 0 120px rgb(229 72 77 / 55%);
  animation: k-alert-breath 2.4s ease-in-out infinite;
}

@keyframes k-alert-breath {
  0%,
  100% {
    opacity: 0.35;
  }

  50% {
    opacity: 1;
  }
}

/* 荧光波形带：轮播下方通栏，固定深色底（kiosk 不用 .nd 令牌） */
.k-band-wrap {
  position: relative;
  height: 64px;
  margin-top: 8px;
  overflow: hidden;
  background: rgb(13 15 20 / 65%);
  border: 1px solid #1c1e26;
  border-radius: 10px;
}

.k-band {
  display: block;
  width: 100%;
  height: 100%;
}

.k-band-tag {
  position: absolute;
  top: 6px;
  right: 12px;
  font-size: 10px;
  letter-spacing: 0.12em;
  opacity: 0.85;

  &.net {
    right: 48px;
    color: #3fb68b;
  }
}

.k-footbar {
  display: flex;
  gap: 20px;
  align-items: center;
  justify-content: flex-end;
  min-height: 34px;
}

.k-dots {
  display: flex;
  gap: 8px;
  margin-right: auto;
}

.k-dot-i {
  width: 8px;
  height: 8px;
  background: #26282f;
  border-radius: 50%;
  transition: background 300ms ease;

  &.on {
    background: #f15a2c;
  }
}

.k-exit,
.k-hint {
  font-size: 13px;
  color: #8b8d95;
  opacity: 0;
  transition: opacity 300ms ease;
}

.k-exit {
  padding: 7px 16px;
  cursor: pointer;
  background: #14161c;
  border: 1px solid #26282f;
  border-radius: 8px;

  &.show {
    opacity: 1;
  }

  &:hover {
    color: #e8ecf4;
    border-color: #3a3d47;
  }
}

.k-hint.show {
  opacity: 1;
}

/* 径向擦除转场（花活二期 P）：clip-path 圆形展开/收拢；reduced-motion 回退纯淡入淡出 */
.kfade-enter-active,
.kfade-leave-active {
  transition:
    clip-path 600ms ease,
    opacity 400ms ease;
}

.kfade-enter-from {
  clip-path: circle(0% at 50% 50%);
  opacity: 0.4;
}

.kfade-enter-to {
  clip-path: circle(75% at 50% 50%);
}

.kfade-leave-to {
  clip-path: circle(0% at 50% 50%);
  opacity: 0.2;
}

.kfade-leave-from {
  clip-path: circle(75% at 50% 50%);
}

@media (prefers-reduced-motion: reduce) {
  .kfade-enter-active,
  .kfade-leave-active {
    clip-path: none;
    transition: opacity 300ms ease;
  }

  .kfade-enter-from,
  .kfade-leave-to {
    clip-path: none;
  }

  .k-alert-glow {
    opacity: 0.7;
    animation: none;
  }
}
</style>
