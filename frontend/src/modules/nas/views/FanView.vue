<script setup>
/** 风扇控制：接管总开关 + 手动调速卡 + 曲线编辑器 + 温控规则（后端 + 演示回退） */
import { computed, reactive, ref, watch } from 'vue';
import { fans as mockFans } from '../mock';
import { apiData } from '../api/client';
import { useViewData } from '../composables/useViewData';
import * as nasData from '../api/data';
import UPageHeader from '../components/UPageHeader.vue';
import UPop from '../components/UPop.vue';
import UCurveEditor from '../components/UCurveEditor.vue';
import FanRotor from '../components/FanRotor.vue';

defineOptions({ name: 'NasFan' });

const { data: d, live } = useViewData(nasData.fetchFans, mockFans);

/** 接管总开关（真实控区存在时走后端 fcs/mode；演示模式仅本地态） */
const takeoverOverride = ref(null);
const takeover = computed(() => takeoverOverride.value ?? d.value.takeover ?? true);
const takeoverPopOpen = ref(false);

function toggleTakeover() {
  if (takeover.value) {
    takeoverPopOpen.value = true; // 开 → 关需二次确认
  } else {
    takeoverOverride.value = true;
    if (live.value) apiData('/api/v1/control/fcs/takeover', { method: 'POST' }).catch(() => null);
  }
}

async function confirmTakeoverOff() {
  takeoverOverride.value = false;
  if (live.value) {
    await apiData('/api/v1/control/fcs/release', { method: 'POST' }).catch(() => null);
  }
}

/** 风扇卡：滑杆 → 转速/占空比/扇叶转速联动（数据加载后重建，滑杆可编辑） */
const cards = reactive([]);
watch(
  () => d.value.cards,
  (list) => {
    cards.splice(0, cards.length, ...list.map((c) => ({ ...c })));
  },
  { immediate: true, deep: true }
);

function rotorDur(duty) {
  return Math.max(0.35, 6 - duty * 0.05);
}

function rotorRpm(duty) {
  return Math.round(duty * 26.5);
}

/** 曲线编辑器（后端有曲线时回填，保存走 PUT /control/curves/{id}） */
const curvePts = ref(mockFans.curveDefault.map((p) => [...p]));
const curveReadout = ref(null);
const savingCurve = ref(false);
const curveSaved = ref(false);

watch(
  () => d.value.curveDefault,
  (pts) => {
    if (pts?.length) curvePts.value = pts.map((p) => [...p]);
  },
  { immediate: true }
);

function onCurveDrag(p) {
  curveReadout.value = { t: p[0], duty: p[1] };
}

function curveAdd() {
  const pts = curvePts.value;
  let bi = 0;
  let bw = -1;
  for (let i = 0; i < pts.length - 1; i += 1) {
    const w = pts[i + 1][0] - pts[i][0];
    if (w > bw) {
      bw = w;
      bi = i;
    }
  }
  const next = pts.map((p) => [...p]);
  next.splice(bi + 1, 0, [
    Math.round((next[bi][0] + next[bi + 1][0]) / 2),
    Math.round((next[bi][1] + next[bi + 1][1]) / 2),
  ]);
  curvePts.value = next;
}

function curveReset() {
  curvePts.value = (d.value.curveDefault ?? mockFans.curveDefault).map((p) => [...p]);
  curveReadout.value = null;
  curveSaved.value = false;
}

async function saveCurve() {
  curveSaved.value = false;
  if (!live.value || d.value.curveId == null) return;
  savingCurve.value = true;
  try {
    await apiData(`/api/v1/control/curves/${d.value.curveId}`, {
      method: 'PUT',
      body: { name: '默认曲线', points: curvePts.value, hysteresis_c: 2, ramp_per_tick: 5 },
    });
    curveSaved.value = true;
  } catch {
    /* 校验失败（1002）静默，气泡读数可自查 */
  } finally {
    savingCurve.value = false;
  }
}

const headerTag = computed(() =>
  takeover.value
    ? { type: 'acc', text: live.value ? '接管中' : '接管中 · 演示' }
    : { type: 'warn', text: '已交还' }
);
</script>

<template>
  <section>
    <u-page-header
      title="风扇控制"
      sub="接管 · 手动调速 · 温控规则 · 曲线编辑"
      :tag="headerTag"
      updated="10:32:09"
    >
      <template #right>
        <label class="switch on" @click.prevent> <span class="tr" />2s </label>
      </template>
    </u-page-header>

    <!-- 接管总开关 -->
    <div class="wg">
      <div class="wg-b opcard" style="padding: 14px 16px">
        <label class="switch" :class="{ on: takeover }" @click="toggleTakeover">
          <span class="tr" />
        </label>
        <div class="ot" style="flex: 1; min-width: 220px">
          <b>风扇接管总开关</b>
          <small
            >开启后由 nasdeck 接管全部风扇（自动停止 FCS / 关闭时恢复）；启停均需二次确认</small
          >
        </div>
        <div class="oa">
          <u-pop
            v-model="takeoverPopOpen"
            ok-text="停用"
            cancel-text="取消"
            danger
            @confirm="confirmTakeoverOff"
          >
            <template #trigger>
              <button class="btn sm" :disabled="!takeover">停用接管</button>
            </template>
            确认停用风扇接管？将交还主板 BIOS 控制（FCS 恢复）。
          </u-pop>
        </div>
      </div>
    </div>

    <!-- 手动调速卡 -->
    <div class="grid">
      <div v-for="fan in cards" :key="fan.name" class="wg t4 fan-card">
        <div class="wg-h">
          <u-icon name="fan" />
          <h3>{{ fan.name }}</h3>
          <span class="x">
            <button class="btn sm">重命名</button>
            <button class="btn sm">隐藏</button>
          </span>
        </div>
        <div class="wg-b">
          <div class="fanrow">
            <fan-rotor size="lg" :dur-sec="rotorDur(fan.duty)" :paused="fan.duty === 0" />
            <span class="big num">{{ rotorRpm(fan.duty) }}<small> RPM</small></span>
            <span class="num">占空比 {{ fan.duty }}%</span>
          </div>
          <input v-model.number="fan.duty" type="range" min="0" max="100" :disabled="!takeover" />
          <div class="dutyrow">
            <label class="switch" :class="{ on: fan.pwm }" @click="fan.pwm = !fan.pwm">
              <span class="tr" />PWM
            </label>
            <span>DC 12V</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 曲线编辑器 + 温控规则 -->
    <div class="grid" style="margin-bottom: 0">
      <div class="wg t8">
        <div class="wg-h">
          <u-icon name="pulse" />
          <h3>风扇曲线编辑器</h3>
          <span class="x">
            <span class="readout num">
              <template v-if="curveReadout">
                温度 <b>{{ curveReadout.t }} °C</b> → 占空比 <b>{{ curveReadout.duty }}%</b>
              </template>
              <template v-else>拖拽圆点调整</template>
            </span>
            <button class="btn sm" @click="curveAdd"><u-icon name="plus" />添加点</button>
            <button class="btn sm" @click="curveReset">重置</button>
          </span>
        </div>
        <div class="wg-b curve-wrap">
          <u-curve-editor v-model="curvePts" @drag="onCurveDrag" />
        </div>
      </div>

      <div class="wg t4">
        <div class="wg-h">
          <u-icon name="shield" />
          <h3>温控规则</h3>
        </div>
        <div class="wg-b">
          <template v-for="(rule, ri) in d.rules" :key="rule.title">
            <div class="small" style="margin-bottom: 8px; font-weight: 600">{{ rule.title }}</div>
            <div class="frm" :style="ri < d.rules.length - 1 ? 'margin-bottom: 15px' : ''">
              <label>传感器</label>
              <select>
                <option>{{ rule.sensor }}</option>
              </select>
              <label>曲线</label>
              <select>
                <option>{{ rule.curve }}</option>
              </select>
              <label>迟滞</label>
              <input type="text" :value="rule.hysteresis" />
            </div>
          </template>
          <button
            class="btn pri"
            style="margin-top: 15px"
            :disabled="savingCurve"
            @click="saveCurve"
          >
            <u-icon name="check" />{{
              savingCurve ? '保存中…' : curveSaved ? '已保存' : '保存规则'
            }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
