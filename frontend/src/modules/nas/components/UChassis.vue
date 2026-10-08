<script setup>
/**
 * 机箱热力图（花活 F）：2D 机箱示意——主板/CPU/电源/硬盘笼摆块按温度着色，
 * 风扇条气流动画随实际转速调速，盘位点击看详情。
 * 传感器芯片可在「编辑布局」中拖放到主板开阔区（网格吸附），布局存 localStorage；
 * 未定位传感器在托盘区照常显示（不藏数据）。纯前端组件，零新增采集。
 */
import { computed, ref, watch } from 'vue';
import { tempClass } from '../utils/format';
import UIcon from './UIcon.vue';
import UModal from './UModal.vue';

defineOptions({ name: 'UChassis' });

const props = defineProps({
  /** 温度传感器：{ key, label, zone, celsius, grade } */
  sensors: { type: Array, default: () => [] },
  /** 风区：{ id, name, rpm, duty } */
  fans: { type: Array, default: () => [] },
  /** 硬盘：{ slot, device, model, capacity, tempC, health, kind, serial } */
  disks: { type: Array, default: () => [] },
  warmAt: { type: Number, default: 45 },
  hotAt: { type: Number, default: 60 },
});

/** 网格 12×8；可放置区为主板开阔区（避开左右风扇条与底部电源/硬盘笼） */
const AREA = { x1: 2, x2: 11, y1: 1, y2: 5 };
const STORAGE_KEY = 'nd_chassis_layout_v1';
const MAX_SLOTS = 12;
const MAX_FANS_PER_SIDE = 4;

/** 各 zone 默认落点序列（数组为 [x, y]，row/col 语义见 gridArea 绑定） */
const DEFAULT_SPOTS = {
  // CPU 落点从第 2 行起：第 1 行留给区域标签，避免默认布局即遮字
  cpu: [
    [3, 2],
    [4, 2],
    [5, 2],
    [3, 3],
    [4, 3],
    [5, 3],
  ],
  board: [
    [6, 1],
    [7, 1],
    [8, 1],
    [9, 1],
    [6, 2],
    [7, 2],
    [8, 2],
    [9, 2],
    [6, 3],
    [7, 3],
    [8, 3],
    [9, 3],
    [10, 1],
    [10, 2],
    [10, 3],
  ],
  nvme: [
    [3, 4],
    [4, 4],
    [5, 4],
    [6, 4],
    [7, 4],
  ],
  other: [
    [8, 4],
    [9, 4],
    [10, 4],
    [2, 2],
    [2, 3],
    [2, 4],
  ],
  // 硬盘区传感器不默认摆位：盘温已由硬盘笼展示，避免双重表达
  disk: [],
};

const pos = ref({}); // sensorKey → [x, y]
const editing = ref(false);
const dragKey = ref(null);
const hoverCell = ref('');

function loadStore() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    return raw?.v === 1 && raw.pos ? raw.pos : {};
  } catch {
    return {};
  }
}

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ v: 1, pos: pos.value }));
}

const inArea = ([x, y]) => x >= AREA.x1 && x <= AREA.x2 && y >= AREA.y1 && y <= AREA.y2;
const cellKey = (x, y) => `${x},${y}`;

/** 布局收敛：存量布局有效则保留，新传感器按 zone 补默认位，冲突/越界回托盘 */
function relayout() {
  const stored = loadStore();
  const next = {};
  const used = new Set();
  for (const s of props.sensors) {
    const p = stored[s.key];
    if (Array.isArray(p) && inArea(p) && !used.has(cellKey(...p))) {
      next[s.key] = p;
      used.add(cellKey(...p));
    }
  }
  const cursor = {};
  for (const s of props.sensors) {
    if (next[s.key]) continue;
    const spots = DEFAULT_SPOTS[s.zone] ?? [];
    let i = cursor[s.zone] ?? 0;
    while (i < spots.length && used.has(cellKey(...spots[i]))) i++;
    cursor[s.zone] = i;
    if (i < spots.length) {
      next[s.key] = spots[i];
      used.add(cellKey(...spots[i]));
      cursor[s.zone] = i + 1;
    }
  }
  pos.value = next;
}

watch(() => props.sensors, relayout, { immediate: true });

const placedSensors = computed(() =>
  props.sensors.filter((s) => pos.value[s.key]).map((s) => ({ ...s, xy: pos.value[s.key] }))
);
const tray = computed(() => props.sensors.filter((s) => !pos.value[s.key]));

const occupied = computed(() => {
  const set = new Set();
  for (const p of Object.values(pos.value)) set.add(cellKey(...p));
  return set;
});

const editCells = computed(() => {
  const cells = [];
  for (let y = AREA.y1; y <= AREA.y2; y++) {
    for (let x = AREA.x1; x <= AREA.x2; x++) cells.push({ x, y });
  }
  return cells;
});

/* ---- 拖拽布局（HTML5 DnD，芯片可从托盘拖入、拖回托盘移除） ---- */
function dragStart(key, e) {
  dragKey.value = key;
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', key);
}
function dragEnd() {
  dragKey.value = null;
  hoverCell.value = '';
}
function dropCell(x, y) {
  const key = dragKey.value;
  dragKey.value = null;
  hoverCell.value = '';
  if (!key) return;
  const occupiedBy = Object.entries(pos.value).find(
    ([k, p]) => p[0] === x && p[1] === y && k !== key
  );
  if (occupiedBy) return; // 占用格拒落，光标已给 not-allowed 反馈
  pos.value = { ...pos.value, [key]: [x, y] };
  persist();
}
function dropTray() {
  const key = dragKey.value;
  dragKey.value = null;
  hoverCell.value = '';
  if (!key) return;
  const { [key]: _drop, ...rest } = pos.value;
  pos.value = rest;
  persist();
}
function resetLayout() {
  localStorage.removeItem(STORAGE_KEY);
  relayout();
}

/* ---- 风扇与气流 ---- */
/** 转速 → 动画周期 ms：1200RPM≈1.4s，限幅 0.5–6s；0 转静止 */
function spinDur(rpm) {
  if (!rpm) return 0;
  return Math.min(6000, Math.max(500, (1200 * 1200) / rpm));
}
const fanSides = computed(() => {
  const left = [];
  const right = [];
  props.fans.forEach((f, i) => (i % 2 === 0 ? left : right).push(f));
  return {
    left: left.slice(0, MAX_FANS_PER_SIDE),
    right: right.slice(0, MAX_FANS_PER_SIDE),
    leftOver: Math.max(0, left.length - MAX_FANS_PER_SIDE),
    rightOver: Math.max(0, right.length - MAX_FANS_PER_SIDE),
  };
});
const maxRpm = computed(() => Math.max(0, ...props.fans.map((f) => f.rpm ?? 0)));
const flowDur = computed(() => spinDur(maxRpm.value));
const hasFlow = computed(() => props.fans.some((f) => (f.rpm ?? 0) > 0));
const fanTip = (f) => `${f.name} · ${f.rpm ?? 0} RPM · 占空比 ${f.duty ?? 0}%`;
const overTip = (names) => `其余 ${names.length} 个风扇：${names.join('、')}`;

/* ---- 硬盘笼 ---- */
const slotCount = computed(() => {
  const maxSlot = Math.max(0, ...props.disks.map((d) => d.slot ?? 0));
  return Math.min(MAX_SLOTS, Math.max(maxSlot, props.disks.length));
});
const slots = computed(() =>
  Array.from({ length: slotCount.value }, (_, i) => ({
    n: i + 1,
    disk: props.disks.find((d) => d.slot === i + 1) ?? null,
  }))
);
const hiddenDisks = computed(() => Math.max(0, props.disks.length - MAX_SLOTS));
const diskTip = (d) =>
  `${d.device} · ${d.model} · ${d.tempC != null ? `${d.tempC}°C` : '—'} · ${d.health}`;

/* ---- 盘位详情弹窗 ---- */
const selDisk = ref(null);
const diskModal = ref(false);
function openDisk(disk) {
  if (!disk) return;
  selDisk.value = disk;
  diskModal.value = true;
}

/** 传感器着色：以后端 grade 为准（无 grade 兜底按温度分档） */
function gradeOf(s) {
  if (s.grade === 'warm' || s.grade === 'hot' || s.grade === 'critical') return s.grade;
  return tempClass(s.celsius, props.warmAt, props.hotAt) || 'normal';
}
</script>

<template>
  <div class="wg">
    <div class="wg-h">
      <u-icon name="temp" />
      <h3>机箱热力图</h3>
      <span class="x">传感器按温度着色 · 气流随实际转速</span>
      <span class="acts">
        <template v-if="editing">
          <button class="btn sm" @click="resetLayout"><u-icon name="refresh" />重置布局</button>
          <button class="btn sm pri" @click="editing = false"><u-icon name="check" />完成</button>
        </template>
        <button v-else class="btn sm" @click="editing = true">
          <u-icon name="plus" />编辑布局
        </button>
      </span>
    </div>
    <div class="wg-b">
      <p v-if="editing" class="edit-hint">
        拖动传感器芯片摆放到主板开阔区；拖回下方托盘移出机箱；占用格不可落。
      </p>

      <div class="chassis-scroll">
        <div class="chassis" :class="{ editing }">
          <!-- 气流走廊：进风→排风，速度随最高转速 -->
          <div v-if="hasFlow" class="flow" :style="{ '--fdur': `${flowDur}ms` }" aria-hidden="true">
            <i /><i /><i />
          </div>

          <div class="rg rg-mb"><span>主板</span></div>
          <div class="rg rg-cpu"><span>CPU</span></div>
          <div class="rg rg-psu"><span>电源</span></div>
          <div class="rg rg-cage">
            <span>硬盘笼</span>
            <div class="slots">
              <div
                v-for="sl in slots"
                :key="sl.n"
                class="slot"
                :class="[
                  sl.disk ? tempClass(sl.disk.tempC, warmAt, hotAt) : 'empty',
                  { has: !!sl.disk },
                ]"
                :data-tip="sl.disk ? diskTip(sl.disk) : `盘位 ${sl.n} · 空`"
                :style="sl.disk && sl.disk.tempC == null ? 'opacity:.75' : ''"
                @click="openDisk(sl.disk)"
              >
                <template v-if="sl.disk">
                  <b>{{ sl.disk.tempC != null ? `${sl.disk.tempC}°` : '—' }}</b>
                  <i>盘{{ sl.n }}</i>
                </template>
                <template v-else
                  ><i>空位 {{ sl.n }}</i></template
                >
              </div>
              <span
                v-if="hiddenDisks"
                class="slot-more"
                :data-tip="`其余 ${hiddenDisks} 块盘请到硬盘页查看`"
              >
                +{{ hiddenDisks }}
              </span>
              <span v-if="!disks.length" class="rg-empty">无硬盘读数</span>
            </div>
          </div>

          <div class="fstrip left">
            <div
              v-for="f in fanSides.left"
              :key="f.id"
              class="fan"
              :class="{ idle: !f.rpm }"
              :style="{ '--sdur': spinDur(f.rpm) + 'ms' }"
              :data-tip="fanTip(f)"
            >
              <svg class="ico"><use href="#nd-i-fan" /></svg>
              <i>{{ f.rpm ?? 0 }}</i>
            </div>
            <span
              v-if="fanSides.leftOver"
              class="fan-more"
              :data-tip="overTip(fanSides.left.slice(MAX_FANS_PER_SIDE).map((f) => f.name))"
            >
              +{{ fanSides.leftOver }}
            </span>
          </div>
          <div class="fstrip right">
            <div
              v-for="f in fanSides.right"
              :key="f.id"
              class="fan"
              :class="{ idle: !f.rpm }"
              :style="{ '--sdur': spinDur(f.rpm) + 'ms' }"
              :data-tip="fanTip(f)"
            >
              <svg class="ico"><use href="#nd-i-fan" /></svg>
              <i>{{ f.rpm ?? 0 }}</i>
            </div>
            <span
              v-if="fanSides.rightOver"
              class="fan-more"
              :data-tip="overTip(fanSides.right.slice(MAX_FANS_PER_SIDE).map((f) => f.name))"
            >
              +{{ fanSides.rightOver }}
            </span>
          </div>

          <!-- 编辑态落点网格 -->
          <template v-if="editing">
            <div
              v-for="c in editCells"
              :key="c.x + '-' + c.y"
              class="cell"
              :class="{
                over: hoverCell === cellKey(c.x, c.y),
                block: occupied.has(cellKey(c.x, c.y)),
              }"
              @dragover.prevent="hoverCell = cellKey(c.x, c.y)"
              @dragleave="hoverCell = ''"
              @drop.prevent="dropCell(c.x, c.y)"
            />
          </template>

          <!-- 传感器芯片 -->
          <div
            v-for="s in placedSensors"
            :key="s.key"
            class="chip"
            :class="[`g-${gradeOf(s)}`, { 'tip-b': s.xy[1] === AREA.y1, drag: editing }]"
            :style="{ gridArea: `${s.xy[1]} / ${s.xy[0]}` }"
            :data-tip="`${s.label} · ${s.celsius}°C`"
            :draggable="editing"
            @dragstart="dragStart(s.key, $event)"
            @dragend="dragEnd"
          >
            <i>{{ s.label }}</i>
            <b class="num">{{ s.celsius }}°</b>
          </div>

          <div v-if="!sensors.length" class="chassis-empty">后端暂无温度传感器读数</div>
        </div>
      </div>

      <!-- 未定位托盘：查看态照常展示读数，编辑态可拖入机箱 -->
      <div
        v-if="tray.length || editing"
        class="tray"
        :class="{ editing }"
        @dragover.prevent
        @drop.prevent="dropTray"
      >
        <span class="tray-cap">未定位 {{ tray.length }}</span>
        <div
          v-for="s in tray"
          :key="s.key"
          class="chip mini"
          :class="[`g-${gradeOf(s)}`, { drag: editing }]"
          :data-tip="`${s.label} · ${s.celsius}°C`"
          :draggable="editing"
          @dragstart="dragStart(s.key, $event)"
          @dragend="dragEnd"
        >
          <i>{{ s.label }}</i>
          <b class="num">{{ s.celsius }}°</b>
        </div>
      </div>

      <div class="legend">
        <span><i style="background: var(--sf3)" />&lt; {{ warmAt }} 正常</span>
        <span
          ><i style="background: var(--warnbg); border: 1px solid var(--warn)" />{{ warmAt }} –
          {{ hotAt }} 偏高</span
        >
        <span
          ><i style="background: var(--badbg); border: 1px solid var(--bad)" />&gt;
          {{ hotAt }} 过热</span
        >
        <span class="lg-flow"><i class="flow-dot" />气流方向 进→排</span>
      </div>
    </div>

    <u-modal
      v-model="diskModal"
      :title="selDisk ? `盘位 ${selDisk.slot} · ${selDisk.device}` : ''"
      icon="drive"
    >
      <table v-if="selDisk" class="dkv">
        <tbody>
          <tr>
            <td>型号</td>
            <td>{{ selDisk.model }}</td>
          </tr>
          <tr>
            <td>容量</td>
            <td>{{ selDisk.capacity }}</td>
          </tr>
          <tr>
            <td>介质</td>
            <td>{{ selDisk.kind }}</td>
          </tr>
          <tr>
            <td>温度</td>
            <td>
              <span class="num" :class="tempClass(selDisk.tempC, warmAt, hotAt)">
                {{ selDisk.tempC != null ? `${selDisk.tempC} °C` : '—' }}
              </span>
            </td>
          </tr>
          <tr>
            <td>健康</td>
            <td>{{ selDisk.health }}</td>
          </tr>
          <tr>
            <td>序列号</td>
            <td>{{ selDisk.serial || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p class="dkv-hint">SMART 详情与在线自检请到「硬盘」页。</p>
    </u-modal>
  </div>
</template>

<style scoped lang="scss">
.chassis-scroll {
  padding-bottom: 4px;
  overflow-x: auto;
}

.chassis {
  position: relative;
  display: grid;
  grid-template-rows: repeat(8, 44px);
  grid-template-columns: repeat(12, 1fr);
  gap: 4px;
  min-width: 780px;
  padding: 10px;
  background: var(--sf);
  border: 1px solid var(--bd);
  border-radius: var(--r);
}

/* 区域摆块 */
.rg {
  position: relative;
  z-index: 1;
  padding: 18px 8px 6px;
  border: 1px dashed var(--bd2);
  border-radius: var(--r-s);

  > span {
    position: absolute;
    top: 4px;
    left: 8px;
    font-size: 10px;
    font-weight: 600;
    color: var(--tx3);
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  &.rg-mb {
    grid-area: 1 / 2 / 6 / 12;
  }

  &.rg-cpu {
    grid-area: 1 / 3 / 4 / 6;
    background: var(--sf2);
  }

  &.rg-psu {
    display: flex;
    grid-area: 6 / 2 / 9 / 5;
    align-items: center;
    justify-content: center;
    color: var(--tx3);
    background: var(--sf2);

    > span {
      position: static;
      font-size: 12px;
      letter-spacing: 2px;
    }
  }

  &.rg-cage {
    grid-area: 6 / 6 / 9 / 12;
  }
}

.rg-empty {
  align-self: center;
  font-size: 12px;
  color: var(--tx3);
}

/* 气流走廊 */
.flow {
  position: absolute;
  inset: 6% 2% 6% 6%;
  z-index: 0;
  pointer-events: none;
  mask-image: linear-gradient(90deg, transparent, #000 12%, #000 88%, transparent);

  i {
    position: absolute;
    right: 0;
    left: 0;
    height: 2px;
    background: repeating-linear-gradient(
      90deg,
      transparent 0 16px,
      var(--accbg) 16px 22px,
      var(--acc) 22px 28px,
      var(--accbg) 28px 34px
    );
    opacity: 0.55;
    animation: ch-flow var(--fdur, 2s) linear infinite;

    &:nth-child(1) {
      top: 22%;
    }

    &:nth-child(2) {
      top: 50%;
      opacity: 0.35;
    }

    &:nth-child(3) {
      top: 78%;
      opacity: 0.45;
    }
  }
}

@keyframes ch-flow {
  to {
    background-position-x: 56px;
  }
}

/* 风扇条 */
.fstrip {
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px 0;

  &.left {
    grid-area: 1 / 1 / 9 / 2;
  }
  &.right {
    grid-area: 1 / 12 / 9 / 13;
  }
}

.fan {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  justify-content: center;
  color: var(--acc);
  cursor: default;
  background: var(--sf2);
  border: 1px solid var(--bd2);
  border-radius: var(--r-s);

  .ico {
    width: 18px;
    height: 18px;
    animation: ch-spin var(--sdur, 2s) linear infinite;
  }

  i {
    font-size: 9px;
    font-style: normal;
    color: var(--tx2);
  }

  &.idle .ico {
    color: var(--tx3);
    animation: none;
  }
}

.fan-more,
.slot-more {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--tx2);
  cursor: default;
  background: var(--sf2);
  border: 1px dashed var(--bd2);
  border-radius: var(--r-s);
}

.fan-more {
  flex: none;
  min-height: 26px;
}

.slot-more {
  padding: 0 8px;
}

@keyframes ch-spin {
  to {
    transform: rotate(360deg);
  }
}

/* 编辑态落点格 */
.cell {
  z-index: 2;
  border: 1px dashed transparent;
  border-radius: var(--r-s);
  transition:
    border-color var(--t) var(--ease),
    background var(--t) var(--ease);

  &.over {
    background: var(--accbg);
    border-color: var(--acc);
  }

  &.block.over {
    cursor: not-allowed;
    background: var(--badbg);
    border-color: var(--bad);
  }
}

/* 传感器芯片 */
.chip {
  position: relative;
  z-index: 3;
  display: flex;
  flex-direction: column;
  gap: 1px;
  align-items: center;
  justify-content: center;
  min-width: 0;
  overflow: visible;
  border-radius: var(--r-s);
  transition:
    box-shadow var(--t) var(--ease),
    transform var(--t) var(--ease);

  i {
    max-width: 100%;
    overflow: hidden;
    font-size: 10px;
    font-style: normal;
    color: var(--tx2);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  b {
    font-size: 14px;
  }

  &.g-normal {
    background: var(--okbg);
    border: 1px solid var(--ok);
  }

  &.g-warm {
    background: var(--warnbg);
    border: 1px solid var(--warn);
  }

  &.g-hot,
  &.g-critical {
    background: var(--badbg);
    border: 1px solid var(--bad);

    i {
      color: var(--tx1);
    }
  }

  &.mini {
    flex: none;
    flex-direction: row;
    gap: 6px;
    height: 28px;
    padding: 0 9px;
  }

  &.drag {
    cursor: grab;

    &:active {
      cursor: grabbing;
    }

    &:hover {
      box-shadow: var(--shadow);
      transform: translateY(-1px);
    }
  }

  &:not(.drag) {
    cursor: default;
  }
}

.chassis-empty {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--tx3);
}

.edit-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--tx2);
}

/* 未定位托盘 */
.tray {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  min-height: 40px;
  padding: 6px 8px;
  margin-top: 10px;
  background: var(--sf);
  border: 1px dashed var(--bd2);
  border-radius: var(--r-s);

  &.editing {
    border-color: var(--acc-d);
  }
}

.tray-cap {
  margin-right: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--tx3);
}

.acts {
  display: inline-flex;
  gap: 6px;
  margin-left: auto;
}

.btn.sm {
  height: 26px;
  padding: 0 9px;
  font-size: 12px;
  border-radius: var(--r-s);
}

/* 悬停读数气泡 */
.chip,
.slot,
.fan,
.fan-more,
.slot-more {
  &[data-tip] {
    position: relative;

    &::after {
      position: absolute;
      bottom: calc(100% + 6px);
      left: 50%;
      z-index: 40;
      padding: 4px 8px;
      font-size: 11px;
      color: var(--tx0);
      white-space: nowrap;
      pointer-events: none;
      content: attr(data-tip);
      background: var(--tt);
      border: 1px solid var(--ttbd);
      border-radius: 5px;
      opacity: 0;
      transition:
        opacity var(--t) var(--ease),
        transform var(--t) var(--ease);
      transform: translateX(-50%) scale(0.96);
    }

    &:hover::after {
      opacity: 1;
      transform: translateX(-50%) scale(1);
    }
  }
}

.chip.tip-b[data-tip]::after {
  top: calc(100% + 6px);
  bottom: auto;
}

/* 硬盘笼盘位 */
.slots {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: stretch;
  height: 100%;
}

.slot {
  display: flex;
  flex: 1 1 64px;
  flex-direction: column;
  gap: 1px;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  max-width: 96px;
  padding: 3px 4px;
  border-radius: var(--r-s);

  i {
    font-size: 9px;
    font-style: normal;
    color: var(--tx3);
  }

  b {
    font-size: 14px;
  }

  &.has {
    cursor: pointer;
  }

  &.empty {
    color: var(--tx3);
    border: 1px dashed var(--bd);
  }

  &.normal {
    background: var(--okbg);
    border: 1px solid var(--ok);
  }

  &.warm {
    background: var(--warnbg);
    border: 1px solid var(--warn);
  }

  &.hot {
    background: var(--badbg);
    border: 1px solid var(--bad);
  }
}

/* 盘位详情表 */
.dkv {
  width: 100%;
  font-size: 13px;
  border-collapse: collapse;

  td {
    padding: 6px 4px;
    border-bottom: 1px solid var(--bd);

    &:first-child {
      width: 72px;
      color: var(--tx2);
    }
  }

  .num {
    font-weight: 600;

    &.warm {
      color: var(--warn);
    }
    &.hot {
      color: var(--bad);
    }
  }
}

.dkv-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--tx3);
}

.legend {
  display: flex;
  gap: 14px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--tx2);

  span {
    display: inline-flex;
    gap: 5px;
    align-items: center;
  }

  i {
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 3px;
  }

  .flow-dot {
    width: 18px;
    height: 2px;
    background: repeating-linear-gradient(90deg, var(--acc) 0 4px, transparent 4px 8px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .fan .ico,
  .flow i {
    animation: none;
  }
}
</style>
