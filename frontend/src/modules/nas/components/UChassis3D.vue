<script setup>
/** 立体机箱（花活三期 R1）：等距 SVG 渲染器（方案 B，「模型即数据」）——
 * inventory × 模板生成 layout JSON（utils/isochassis/templates.js），渲染器固定不变：
 * 每盒体投影出顶/左/右三面（同一色相三种不透明度 = 烘焙光影），面板色按实时温度
 * 分级（60/75），无源部件灰显悬停显"—"；悬停浮出实时读数 tooltip，点击跳对应页。
 * 纯 2D SVG 无 3D transform——老 WebView 无 z 排序兼容雷区（三期方案比选结论 B）。 */
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  boxFaces,
  boxCenter,
  CAMERA_PRESETS,
  depthCompare,
  iso,
  sceneViewBox,
} from '../utils/isochassis/project';
import { buildLayout, tempGrade } from '../utils/isochassis/templates';

defineOptions({ name: 'UChassis3D' });

const props = defineProps({
  /** inventory：{ board, dimms, nics, sensors, fans, disks }（fetchChassis 形状） */
  sensors: { type: Array, default: () => [] },
  fans: { type: Array, default: () => [] },
  disks: { type: Array, default: () => [] },
  board: { type: Object, default: null },
  dimms: { type: Number, default: 2 },
  nics: { type: Number, default: 1 },
  /** 实时数据（realtime 快照分量）：每盘 IO / 每网口吞吐 / RAPL 功耗 / GPU 可用 */
  io: { type: Object, default: null }, // { <device>: {read_iops, write_iops, ...} }
  net: { type: Object, default: null }, // { <iface>: {rx_kbps, tx_kbps, ...} }
  power: { type: Object, default: null }, // { available, watts }
  gpuAvailable: { type: Boolean, default: false },
  warmAt: { type: Number, default: 60 },
  hotAt: { type: Number, default: 75 },
  // R3：强制模板（auto=DMI 自适配）+ 机位预设 + 分解视图
  template: { type: String, default: 'auto' }, // auto/tower/rack/compact/virtual
  preset: { type: String, default: 'iso' }, // iso/high/side
  explode: { type: Boolean, default: false },
});

const emit = defineEmits(['jump']);
const router = useRouter();
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** layout：纯函数生成（模板自动选择 tower/virtual；R3 提供手动切换与持久化） */
const layout = computed(() =>
  buildLayout(
    {
      sensors: props.sensors,
      fans: props.fans,
      disks: props.disks,
      board: props.board,
      dimms: props.dimms,
      nics: props.nics,
      gpuAvailable: props.gpuAvailable,
    },
    props.template
  )
);

// ---- R3：机位平滑重投影 + 分解系数（rAF 三次缓出插值；reduced-motion 直跳） ----
const projP = ref({ ...CAMERA_PRESETS.iso });
const explodeF = ref(0);
let tweenRaf = 0;

function tween(target, apply) {
  cancelAnimationFrame(tweenRaf);
  if (reduced) {
    apply(1, target);
    return;
  }
  const t0 = performance.now();
  const step = () => {
    const k = Math.min(1, (performance.now() - t0) / 500);
    const e = 1 - (1 - k) ** 3;
    apply(e, target);
    if (k < 1) tweenRaf = requestAnimationFrame(step);
  };
  tweenRaf = requestAnimationFrame(step);
}
watch(
  () => props.preset,
  (name) => {
    const target = CAMERA_PRESETS[name] ?? CAMERA_PRESETS.iso;
    const fromP = { ...projP.value };
    tween(target, (e, t) => {
      projP.value = {
        kx: fromP.kx + (t.kx - fromP.kx) * e,
        ky: fromP.ky + (t.ky - fromP.ky) * e,
        kz: fromP.kz + (t.kz - fromP.kz) * e,
      };
    });
  },
  { immediate: true }
);
watch(
  () => props.explode,
  (on) => {
    const f0 = explodeF.value;
    tween(on ? 1 : 0, (e, t) => {
      explodeF.value = f0 + (t - f0) * e;
    });
  }
);

const viewBox = computed(() =>
  sceneViewBox(layout.value.size, 2.5 + explodeF.value * 5, projP.value)
);

/** 深度排序后的可见盒体（含三面投影点串与数据绑定求值） */
const drawn = computed(() =>
  [...layout.value.boxes].sort(depthCompare).map((b0) => {
    const p = projP.value;
    const f = explodeF.value;
    let b = b0;
    if (f > 0) {
      const size = layout.value.size;
      b = {
        ...b0,
        x: b0.x + (b0.x + b0.w / 2 - size.w / 2) * f * 0.6,
        y: b0.y + (b0.y + b0.d / 2 - size.d / 2) * f * 0.6,
        z: b0.z + (b0.z + b0.h / 2) * f * 0.45,
      };
    }
    const bind = b.bind ?? {};
    let celsius = bind.celsius ?? null;
    let iops = null;
    let watts = null;
    let kbps = null;
    if (bind.type === 'bay' && bind.device) {
      celsius = bind.celsius;
      iops = props.io?.[bind.device] ?? null;
    } else if (bind.type === 'temp') {
      celsius = bind.celsius;
    } else if (bind.type === 'power') {
      watts = props.power?.available ? props.power.watts : null;
    } else if (bind.type === 'net') {
      const vals = Object.values(props.net ?? {});
      const i = bind.index ?? 0;
      kbps = vals[i] ? vals[i].rx_kbps + vals[i].tx_kbps : null;
    } else if (bind.type === 'gpu') {
      celsius = null;
    }
    // 动态层锚点（R2）：扇叶转轴（fan 左面朝观察者）、盘位活动灯（顶面近缘中点）
    let blade = null;
    let led = null;
    if (b.kind === 'fan') {
      blade = iso(b.x + b.w / 2, b.y + b.d, b.z + b.h / 2, p);
    }
    if (b.kind === 'bay') {
      led = iso(b.x + b.w / 2, b.y + b.d, b.z + b.h, p);
    }
    return {
      ...b,
      faces: boxFaces(b, p),
      center: boxCenter(b, p),
      grade: tempGrade(celsius),
      celsius,
      iops,
      watts,
      kbps,
      blade,
      led,
    };
  })
);

// ---- R2 动态层：扇叶转速 / 盘位灯 / 网口闪烁的周期（IOPS·kbps 越高越快，0 静止） ----
function ledStyle(total) {
  if (!total || total <= 0) return null;
  return { '--ldur': `${Math.max(0.16, 1.4 - Math.log10(total + 1) * 0.28).toFixed(2)}s` };
}
function bladeStyle(rpm) {
  if (!rpm || rpm <= 0) return { '--fdur': '3s', animationPlayState: 'paused' };
  return { '--fdur': `${Math.max(0.25, 2.4 - (rpm / 2000) * 2.1).toFixed(2)}s` };
}
function netStyle(kbps) {
  if (!kbps || kbps <= 0) return null;
  return { '--ndur': `${Math.max(0.3, 1.6 - Math.log10(kbps + 1) * 0.3).toFixed(2)}s` };
}

// ---- R2 气流粒子：canvas 叠加层与 SVG 共享同一投影（iso + viewBox 映射），
// 粒子沿 -y 风道自盘笼流向后墙风扇，密度 ∝ 风扇 RPM；页面隐藏即停；reduced-motion 直关
const airCv = ref(null);
const AIR_CAP = 80;
const drops = [];
let airRaf = 0;

function airSpawn() {
  const fans = props.fans ?? [];
  if (!fans.length || drops.length >= AIR_CAP) return;
  const cage = layout.value.boxes.filter((b) => b.kind === 'bay');
  const zone = cage.length
    ? cage
    : layout.value.boxes.filter((b) => b.kind === 'net' || b.kind === 'ram');
  const b = zone[Math.floor(Math.random() * zone.length)];
  if (!b) return;
  drops.push({
    x: b.x + 0.4 + Math.random() * (b.w - 0.8),
    y: b.y + b.d - 0.4,
    z: b.z + 0.6 + Math.random() * 1.2,
    vy: -(0.1 + Math.random() * 0.12),
    life: 0,
  });
}

function worldToPx(pt, cw, ch) {
  const { minX, minY, vw, vh } = viewBox.value;
  const scale = Math.min(cw / vw, ch / vh);
  const ox = (cw - vw * scale) / 2;
  const oy = (ch - vh * scale) / 2;
  return { x: ox + (pt.x - minX) * scale, y: oy + (pt.y - minY) * scale };
}

function airFrame() {
  airRaf = requestAnimationFrame(airFrame);
  const cv = airCv.value;
  if (!cv) return;
  const ctx = cv.getContext('2d');
  const cw = cv.clientWidth;
  const ch = cv.clientHeight;
  if (!cw || !ch) return;
  const dpr = window.devicePixelRatio || 1;
  if (cv.width !== Math.round(cw * dpr) || cv.height !== Math.round(ch * dpr)) {
    cv.width = Math.round(cw * dpr);
    cv.height = Math.round(ch * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cw, ch);
  const fanRpm = (props.fans ?? []).reduce((a, f) => a + (f.rpm || 0), 0);
  if (fanRpm <= 0) return; // 无风扇转速 → 无气流（不造假）
  if (Math.random() < 0.35) airSpawn();
  ctx.fillStyle = paletteAcc;
  for (let i = drops.length - 1; i >= 0; i -= 1) {
    const p = drops[i];
    p.y += p.vy;
    p.z += 0.008;
    p.life += 1;
    if (p.y < 0.6 || p.life > 240) {
      drops.splice(i, 1);
      continue;
    }
    const pt = worldToPx(iso(p.x, p.y, p.z), cw, ch);
    ctx.globalAlpha = Math.max(0.08, 0.4 - p.life / 600);
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, 1.3, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function startAir() {
  if (reduced || airRaf) return;
  airRaf = requestAnimationFrame(airFrame);
}
function stopAir() {
  cancelAnimationFrame(airRaf);
  airRaf = 0;
}

onMounted(() => {
  const cs = getComputedStyle(document.querySelector('.nd') || document.body);
  paletteAcc = cs.getPropertyValue('--acc')?.trim() || '#f15a2c';
  startAir();
});
onActivated(startAir);
onDeactivated(stopAir);
onBeforeUnmount(stopAir);

/** 悬停 tooltip：标签 + 实时读数（无源显"—"） */

const KIND_JUMP = {
  cpu: '/nasdeck/system',
  bay: '/nasdeck/disks',
  fan: '/nasdeck/fan',
  gpu: '/nasdeck/dash',
};

function onClick(box) {
  const to = KIND_JUMP[box.kind] ?? (box.kind === 'net' ? '/nasdeck/ports' : null);
  if (to) router.push(to);
  emit('jump', box);
}

/** 悬停 tooltip：标签 + 实时读数（无源显"—"） */
const hover = ref(null);
let paletteAcc = '#f15a2c';
function tipText(box) {
  const parts = [];
  if (box.kind === 'cpu' || box.kind === 'free' || box.kind === 'm2') {
    parts.push(box.celsius != null ? `${box.celsius} °C` : '—');
  } else if (box.kind === 'bay') {
    parts.push(box.celsius != null ? `${box.celsius} °C` : '—');
    if (box.iops) {
      parts.push(`↓${box.iops.read_iops} ↑${box.iops.write_iops} IOPS`);
    } else {
      parts.push('IO —');
    }
  } else if (box.kind === 'psu') {
    parts.push(box.watts != null ? `${box.watts} W` : '—');
  } else if (box.kind === 'fan') {
    parts.push(`${box.bind?.rpm ?? 0} RPM`);
  } else if (box.kind === 'net') {
    parts.push(box.kbps != null ? `${box.kbps.toFixed(0)} KB/s` : '—');
  } else if (box.tooltip) {
    parts.push(box.tooltip);
  }
  return `${box.label || box.id} · ${parts.join(' · ')}`;
}
</script>

<template>
  <div class="iso">
    <canvas ref="airCv" class="air" />
    <svg
      :viewBox="`${viewBox.minX} ${viewBox.minY} ${viewBox.vw} ${viewBox.vh}`"
      role="img"
      :aria-label="t('立体机箱')"
    >
      <g
        v-for="b in drawn"
        :key="b.id"
        class="box"
        :class="[
          b.kind,
          b.grade,
          { clickable: !!b.label, blink: b.kind === 'net' && (b.kbps ?? 0) > 0 },
        ]"
        :style="b.kind === 'net' ? netStyle(b.kbps) : null"
        @mouseenter="hover = b"
        @mouseleave="hover = null"
        @click="onClick(b)"
      >
        <polygon :points="b.faces.top" class="f top" />
        <polygon :points="b.faces.left" class="f left" />
        <polygon :points="b.faces.right" class="f right" />
        <!-- R2：风扇扇叶（左面转轴，转速 → 周期；0 RPM 静止） -->
        <g
          v-if="b.kind === 'fan' && b.blade"
          class="blades"
          :class="{ still: !(b.bind?.rpm > 0) }"
          :style="bladeStyle(b.bind?.rpm)"
        >
          <circle :cx="b.blade.x" :cy="b.blade.y" r="1.15" class="hub" />
          <g :transform="`rotate(30 ${b.blade.x} ${b.blade.y})`">
            <line
              v-for="a in [0, 60, 120]"
              :key="a"
              :x1="b.blade.x"
              :y1="b.blade.y"
              :x2="b.blade.x + 1.15 * Math.cos((a * Math.PI) / 180)"
              :y2="b.blade.y + 1.15 * Math.sin((a * Math.PI) / 180)"
              class="blade"
            />
          </g>
        </g>
        <!-- R2：盘位活动灯（顶面近缘中点，IOPS → 闪烁周期；无 IO 恒灭） -->
        <circle
          v-if="b.kind === 'bay' && b.led"
          :cx="b.led.x"
          :cy="b.led.y"
          r="0.32"
          class="led"
          :class="{ on: (b.iops?.read_iops ?? 0) + (b.iops?.write_iops ?? 0) > 0 }"
          :style="ledStyle((b.iops?.read_iops ?? 0) + (b.iops?.write_iops ?? 0))"
        />
        <!-- 顶面读数牌：CPU/盘位温度、电源瓦数（无源显"—"，不造假） -->
        <text
          v-if="b.label && (b.kind === 'cpu' || b.kind === 'psu')"
          :x="b.center.x"
          :y="b.center.y + 3"
          class="lbl"
          :class="b.grade"
          text-anchor="middle"
        >
          {{
            b.kind === 'psu'
              ? b.watts != null
                ? `${b.watts}W`
                : '—'
              : b.celsius != null
                ? `${b.celsius}°`
                : '—'
          }}
        </text>
      </g>
    </svg>
    <!-- 悬停读数浮层 -->
    <div v-if="hover" class="tip small num">{{ tipText(hover) }}</div>
    <!-- 模板徽标：当前自动选择的机型视图（R3 提供手动切换与持久化） -->
    <span class="tpl small muted">{{
      layout.kind === 'virtual' ? t('逻辑视图（虚拟机）') : t('塔式侧透')
    }}</span>
  </div>
</template>

<style scoped lang="scss">
.iso {
  position: relative;
  overflow: hidden;
  background: rgb(3 5 8 / 30%);
  border: 1px solid var(--bd);
  border-radius: 10px;

  svg {
    display: block;
    width: 100%;
    height: 460px;
  }

  .air {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }
}

.blades {
  transform-box: fill-box;
  transform-origin: center;
  animation: iso-fan var(--fdur, 1.2s) linear infinite;

  &.still {
    animation-play-state: paused;
  }

  .hub {
    fill: var(--sf3);
    stroke: var(--bd);
    stroke-width: 0.3;
  }

  .blade {
    stroke: var(--tx2);
    stroke-linecap: round;
    stroke-width: 1.1;
  }
}

.led {
  opacity: 0.25;
  fill: var(--sf3);

  &.on {
    fill: var(--acc);
    animation: iso-led var(--ldur, 1s) infinite;
  }
}

.blink {
  animation: iso-net var(--ndur, 1.2s) infinite;
}

@keyframes iso-fan {
  to {
    transform: rotate(360deg);
  }
}

@keyframes iso-led {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.15;
  }
}

@keyframes iso-net {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.35;
  }
}

@media (prefers-reduced-motion: reduce) {
  .blades,
  .led.on,
  .blink {
    animation: none;
  }
}

.f {
  stroke: var(--bd);
  stroke-width: 0.4;

  // 烘焙光影：同色相三种不透明度（顶亮/左中/右暗），主题换装直连
  &.top {
    fill-opacity: 0.92;
  }

  &.left {
    fill-opacity: 0.68;
  }

  &.right {
    fill-opacity: 0.45;
  }
}

.box {
  // 各部件基色（CSS 变量 = 四套主题直连换装）
  polygon {
    fill: var(--sf2);
  }

  &.case polygon {
    fill: var(--sf3);
  }

  &.mobo polygon {
    fill: var(--sf2);
  }

  &.ram polygon {
    fill: var(--info);
  }

  &.m2 polygon,
  &.net polygon {
    fill: var(--info);
  }

  &.psu polygon {
    fill: var(--purp);
  }

  &.fan polygon {
    fill: var(--sf2);
  }

  &.free polygon {
    fill: var(--sf2);
  }

  // 温度分级面色（cpu/bay/m2 顶面按实时温度着色）
  &.cpu polygon,
  &.bay polygon {
    fill: var(--ok);
  }

  &.warm polygon {
    fill: var(--warn);
  }

  &.hot polygon {
    fill: var(--bad);
  }

  &.neutral polygon {
    fill: var(--sf3);
  }

  &.clickable {
    cursor: pointer;

    &:hover .f {
      stroke: var(--acc);
      stroke-width: 0.9;
    }
  }
}

.lbl {
  font-size: 3.6px;
  font-weight: 600;
  pointer-events: none;
  fill: var(--tx0);

  &.neutral {
    fill: var(--tx3);
  }
}

.tip {
  position: absolute;
  top: 10px;
  left: 12px;
  padding: 5px 10px;
  font-size: 12px;
  pointer-events: none;
  background: rgb(0 0 0 / 55%);
  border-radius: 6px;
}

.tpl {
  position: absolute;
  right: 12px;
  bottom: 8px;
}
</style>
