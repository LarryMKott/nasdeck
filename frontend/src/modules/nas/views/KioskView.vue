<script setup>
/** 大屏轮播模式（花活 A）：全屏监控墙——时钟 + 四屏轮播（总览/硬盘/温度/事件）。
 * 独立路由不套 UnraidLayout（无顶栏）；自带深色配色（无 .nd 主题变量）。
 * Esc / 点击呼出退出按钮；轮播间隔 ?sec= 可调（5-60，默认 10）。数据 5s 轮询。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { fetchKiosk } from '../services/monitor';

defineOptions({ name: 'NasKiosk' });

const router = useRouter();

/** 轮播间隔（秒）：?sec= 钳制 5-60 */
const intervalSec = computed(() => {
  const n = parseInt(new URLSearchParams(location.search).get('sec') || '10', 10);
  return Number.isFinite(n) ? Math.min(60, Math.max(5, n)) : 10;
});

const d = ref({ realtime: null, temps: null, disks: null, events: null });
const screenIdx = ref(0);
const now = ref(new Date());
const showExit = ref(false);
const paused = ref(false);

const SCREENS = ['总览', '硬盘', '温度', '事件'];
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
});

onBeforeUnmount(() => {
  clearInterval(pollTimer);
  clearInterval(rotateTimer);
  clearInterval(clockTimer);
  window.removeEventListener('keydown', onKeydown);
  document.documentElement.style.background = '';
});
</script>

<template>
  <div class="kiosk" @mousemove="wakeUi" @click="wakeUi">
    <header class="k-head">
      <div class="k-clock num">{{ clockText }}</div>
      <div class="k-brand">
        <span class="k-logo">nasdeck</span>
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
              <span class="k-label">内存</span>
              <span class="k-big num"
                >{{ rt.mem_percent != null ? rt.mem_percent : '—' }}<i>%</i></span
              >
            </div>
            <div class="k-card">
              <span class="k-label">网速 ↓</span>
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
              <span class="k-label">网速 ↑</span>
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
            <span>负载 {{ (rt.load || []).join(' / ') || '—' }}</span>
            <span>进程 {{ rt.process_count ?? '—' }}</span>
            <span>运行 {{ Math.floor((rt.uptime_s || 0) / 86400) }} 天</span>
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
            </div>
          </div>
          <div v-else class="k-empty">磁盘清单不可用</div>
        </section>

        <!-- 屏 3：温度 -->
        <section v-else-if="screenIdx === 2" key="tp" class="k-screen">
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
          <div v-else class="k-empty">温度传感器不可用</div>
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
          <div v-else class="k-empty">暂无事件（—）</div>
        </section>
      </transition>
    </main>

    <footer class="k-footbar">
      <div class="k-dots">
        <span
          v-for="(name, i) in SCREENS"
          :key="name"
          class="k-dot-i"
          :class="{ on: screenIdx === i }"
          :title="name"
        />
      </div>
      <button class="k-exit" :class="{ show: showExit }" @click="router.push('/nasdeck/dash')">
        退出大屏（Esc）
      </button>
      <span class="k-hint" :class="{ show: showExit }">{{
        paused ? '已暂停' : `${intervalSec}s / 屏`
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

.k-screen {
  width: 100%;
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

.kfade-enter-active,
.kfade-leave-active {
  transition:
    opacity 500ms ease,
    transform 500ms ease;
}

.kfade-enter-from {
  opacity: 0;
  transform: translateY(14px);
}

.kfade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
