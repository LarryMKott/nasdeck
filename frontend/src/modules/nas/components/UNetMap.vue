<script setup>
/** 网络星图（花活二期 L）：canvas 星空——NAS 中心恒星 + 星环亮斑（监听端口，
 * 亮度 = 数量规模）+ 绕轨粒子（ESTABLISHED 连接，内网/外网分色分轨）+ 下方每
 * 网口一条「双向粒子河」（粒子密度与流速 ∝ 真实 rx/tx kbps）。
 * 严格真实口径：粒子只代表连接状态与网口吞吐，不伪造每连接带宽（/proc 不给）。
 * 连接聚合走 /system/network/map（10s 轮询），吞吐走 realtime 快照（1s）。
 * rAF 页面隐藏即停 + keep-alive 启停；prefers-reduced-motion 只画静态帧。 */
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue';
import { useRealtimeStore } from '../stores/realtime';
import { getNetworkMap } from '../api/endpoints/system';
import { networkMap as mockNetworkMap } from '../mock';

defineOptions({ name: 'UNetMap' });

const realtime = useRealtimeStore();
const map = ref({ listening: 0, established: 0, lan: 0, wan: 0, remotes: [] });

async function loadMap() {
  try {
    map.value = await getNetworkMap();
  } catch {
    // 后端不可达：整页演示约定同源——用演示聚合（页面有「演示数据」标签语境）
    map.value = mockNetworkMap;
  }
}

/** 主题色：从 .nd 根读一次（canvas 内不能用 CSS 变量，statusCard 同约定）；
 * 拿不到按默认深色兜底 */
const palette = ref({
  acc: '#f15a2c',
  ok: '#3fb68b',
  warn: '#eca43c',
  info: '#4c8bf5',
  grid: '#2a2c34',
  text: '#8b8d95',
});

function readPalette() {
  const cs = getComputedStyle(document.querySelector('.nd') || document.body);
  const pick = (name, fallback) => cs.getPropertyValue(name)?.trim() || fallback;
  palette.value = {
    acc: pick('--acc', '#f15a2c'),
    ok: pick('--ok', '#3fb68b'),
    warn: pick('--warn', '#eca43c'),
    info: pick('--info', '#4c8bf5'),
    grid: pick('--bd', '#2a2c34'),
    text: pick('--tx2', '#8b8d95'),
  };
}

const canvasEl = ref(null);

// ---- 粒子状态（进程内，随聚合数据重建；预算 <200 满足二期约定） ----
const ORBIT_PARTICLE_CAP = 48;
const orbiters = []; // {ring:'lan'|'wan', ang, speed, size}
const RIVERS_CAP = 64; // 全部河道粒子总数上限
const rivers = ref([]); // {name, rx, tx, drops:[{dir, x, speed, size}]}

function rebuildOrbiters() {
  const want = Math.min(ORBIT_PARTICLE_CAP, map.value.established || 0);
  orbiters.length = 0;
  for (let i = 0; i < want; i += 1) {
    const lanShare = map.value.established ? map.value.lan / map.value.established : 1;
    orbiters.push({
      ring: i < want * lanShare ? 'lan' : 'wan',
      ang: Math.random() * Math.PI * 2,
      speed: 0.004 + Math.random() * 0.01,
      size: 1.2 + Math.random() * 1.6,
    });
  }
}

function rebuildRivers() {
  const net = realtime.snapshot?.net ?? {};
  const lanes = Object.entries(net)
    .filter(([, v]) => v && (v.rx_kbps != null || v.tx_kbps != null))
    .slice(0, 4)
    .map(([name, v]) => ({ name, rx: v.rx_kbps ?? 0, tx: v.tx_kbps ?? 0, drops: [] }));
  rivers.value = lanes;
}

/** 河道粒子目标数：kbps 平方根缩放（1 Mbps 量级 2~3 颗，50 Mbps 量级 ~14 颗） */
function targetDrops(kbps) {
  return kbps > 0 ? Math.min(14, 2 + Math.round(Math.sqrt(kbps) / 2)) : 0;
}

function dropSpeed(kbps) {
  return 0.5 + Math.min(3.2, kbps / 400);
}

// ---- 绘制 ----
let rafId = 0;
let watchdog = 0;
let lastFrame = 0;

function draw() {
  const canvas = canvasEl.value;
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
  const P = palette.value;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // 上半场：星空
  const skyH = h * 0.6;
  const cx = w / 2;
  const cy = skyH / 2 + 6;
  const rLan = Math.min(w, 560) * 0.16;
  const rWan = Math.min(w, 560) * 0.26;

  // 轨道
  ctx.strokeStyle = P.grid;
  ctx.lineWidth = 1;
  ctx.setLineDash([2, 5]);
  for (const r of [rLan, rWan]) {
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  // 中心恒星（NAS）：光晕 + 本体
  const grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, 26);
  grad.addColorStop(0, P.acc);
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(cx, cy, 26, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = P.acc;
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = P.text;
  ctx.font = '11px Inter, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('NAS', cx, cy + 34);

  // 星环亮斑：监听端口（亮斑数 = 规模分档，亮度随规模）
  const spots = Math.min(24, map.value.listening || 0);
  if (spots > 0) {
    const alpha = 0.35 + Math.min(0.5, map.value.listening / 60);
    for (let i = 0; i < spots; i += 1) {
      const ang = (i / spots) * Math.PI * 2 + 0.6;
      const r = i % 2 ? rWan : rLan;
      ctx.fillStyle = P.info;
      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.arc(cx + Math.cos(ang) * r, cy + Math.sin(ang) * r, 1.8, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // 绕轨粒子：ESTABLISHED（内圈 LAN / 外圈 WAN）
  for (const o of orbiters) {
    if (!reduced) o.ang += o.speed;
    const r = o.ring === 'lan' ? rLan : rWan;
    ctx.fillStyle = o.ring === 'lan' ? P.ok : P.warn;
    ctx.shadowColor = ctx.fillStyle;
    ctx.shadowBlur = 5;
    ctx.beginPath();
    ctx.arc(cx + Math.cos(o.ang) * r, cy + Math.sin(o.ang) * r, o.size, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // 图例
  ctx.textAlign = 'left';
  ctx.font = '11px Inter, sans-serif';
  ctx.fillStyle = P.text;
  ctx.fillText(
    `LISTEN ${map.value.listening || 0} · ESTABLISHED ${map.value.established || 0}（LAN ${map.value.lan || 0} / WAN ${map.value.wan || 0}）`,
    12,
    16
  );
  ctx.fillStyle = P.ok;
  ctx.fillRect(w - 118, 10, 6, 6);
  ctx.fillStyle = P.text;
  ctx.fillText('内网', w - 108, 16);
  ctx.fillStyle = P.warn;
  ctx.fillRect(w - 70, 10, 6, 6);
  ctx.fillStyle = P.text;
  ctx.fillText('外网', w - 60, 16);

  // 下半场：每网口双向粒子河
  const laneTop = skyH + 18;
  const laneGap = (h - laneTop - 10) / Math.max(1, rivers.value.length);
  rivers.value.forEach((lane, i) => {
    const y = laneTop + laneGap * (i + 0.5);
    ctx.strokeStyle = P.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(76, y);
    ctx.lineTo(w - 12, y);
    ctx.stroke();
    ctx.fillStyle = P.text;
    ctx.font = '11px Inter, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(lane.name, 12, y + 4);

    // 粒子补给：密度 ∝ kbps（reduced-motion 不生成，静态帧只有轨道与河道）
    if (!reduced && lane.drops.length < RIVERS_CAP) {
      for (const dir of ['rx', 'tx']) {
        const kbps = lane[dir] ?? 0;
        const want = targetDrops(kbps);
        const have = lane.drops.filter((d) => d.dir === dir).length;
        if (have < want && Math.random() < 0.3) {
          lane.drops.push({
            dir,
            x: dir === 'rx' ? 76 : w - 12,
            speed: dropSpeed(kbps),
            size: 1.4 + Math.random(),
          });
        }
      }
    }
    lane.drops = lane.drops.filter((d) => d.x > 70 && d.x < w - 6);
    for (const d of lane.drops) {
      d.x += d.dir === 'rx' ? d.speed : -d.speed; // rx 流入（右→左），tx 流出（左→右）
      ctx.fillStyle = d.dir === 'rx' ? P.ok : P.acc;
      ctx.beginPath();
      ctx.arc(d.x, y, d.size, 0, Math.PI * 2);
      ctx.fill();
    }
    // 读数
    ctx.fillStyle = P.text;
    ctx.textAlign = 'right';
    ctx.fillText(`↓${Math.round(lane.rx)} ↑${Math.round(lane.tx)} KB/s`, w - 12, y - 8);
    ctx.textAlign = 'left';
  });
}

function startLoop() {
  if (rafId || watchdog) return;
  lastFrame = performance.now();
  const tick = () => {
    lastFrame = performance.now();
    draw();
    rafId = requestAnimationFrame(tick);
  };
  rafId = requestAnimationFrame(tick);
  // 看门狗：宿主 rAF 停摆（IAB/遮挡/老 WebView）时 10Hz setInterval 接手
  // （FanRotor 同款护栏；双驱动重入只是同帧多画一次，无正确性影响）
  watchdog = setInterval(() => {
    if (performance.now() - lastFrame > 260) draw();
  }, 100);
}

function stopLoop() {
  cancelAnimationFrame(rafId);
  clearInterval(watchdog);
  rafId = 0;
  watchdog = 0;
}

let mapTimer = 0;

onMounted(() => {
  readPalette();
  loadMap();
  rebuildOrbiters();
  rebuildRivers();
  realtime.acquire();
  startLoop();
  mapTimer = setInterval(() => {
    loadMap();
    rebuildOrbiters();
  }, 10000);
  setInterval(rebuildRivers, 5000);
});

onBeforeUnmount(() => {
  stopLoop();
  clearInterval(mapTimer);
  realtime.release();
});
onActivated(startLoop);
onDeactivated(stopLoop);

const summaryText = computed(
  () =>
    `${t('监听')} ${map.value.listening} · ${t('连接')} ${map.value.established} · ${t('内网')} ${map.value.lan} / ${t('外网')} ${map.value.wan}`
);

defineExpose({ summaryText });
</script>

<template>
  <div class="netmap">
    <canvas ref="canvasEl" class="cv" />
  </div>
</template>

<style scoped>
.netmap {
  overflow: hidden;
  background: rgb(3 5 8 / 35%);
  border: 1px solid var(--bd);
  border-radius: 10px;
}

.cv {
  display: block;
  width: 100%;
  height: 300px;
}
</style>
