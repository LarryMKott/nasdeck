<script setup>
/** 风扇控制：接管总开关 + 手动调速卡 + 曲线编辑器 + 温控规则（后端 + 演示回退） */
import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import * as controlApi from '../api/endpoints/control';
import { useViewData } from '../composables/useViewData';
import { useIdentityStore } from '../stores/identity';
import { fetchFans } from '../services/control';
import UPageHeader from '../components/UPageHeader.vue';
import UPop from '../components/UPop.vue';
import UCurveEditor from '../components/UCurveEditor.vue';
import FanRotor from '../components/FanRotor.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasFan' });

// 权限铁律：设置类操作仅管理员；非管理员全部写控件禁用
const identity = useIdentityStore();
identity.ensure();

// 初始空骨架；mock 仅由适配层在后端不可达时整页演示回退
const {
  data: d,
  live,
  refresh,
  lastUpdated,
} = useViewData(fetchFans, {
  takeover: false,
  cards: [],
  channels: [],
  curveDefault: [],
  curveMeta: null,
  curveId: null,
});

/** 硬件检测：未建风区的 pwm 通道列表，一键创建只读风区（mode=auto 不干预转速） */
const addingKey = ref('');
const loopOf = reactive({});

function detectKey(ch) {
  return `${ch.chip}:${ch.pwm_channel}`;
}

async function addZone(ch) {
  if (!identity.canWrite) return;
  const key = detectKey(ch);
  addingKey.value = key;
  try {
    await controlApi.createFan({
      name: `风扇 pwm${ch.pwm_channel}`,
      loop: loopOf[key] ?? 'chassis',
      hwmon_name: ch.chip,
      pwm_channel: ch.pwm_channel,
      fan_channel: ch.fan_channel,
      mode: 'auto', // 只读监控；调速在卡片上切 PWM/定速或绑曲线
      enabled: true,
    });
    await refresh();
  } catch {
    /* 通道冲突/校验失败静默，列表刷新后以实际状态为准 */
  } finally {
    addingKey.value = '';
  }
}

/** 接管总开关：以后端状态为唯一事实源（本地 override 会吞掉失败请求，
 * 让 UI 显示「已接管」而实际 BIOS 仍在控速——风扇场景这是有后果的撒谎） */
const takeover = computed(() => d.value.takeover ?? false);
const takeoverPopOpen = ref(false);

async function takeoverOn() {
  try {
    await controlApi.takeoverFcs();
  } catch {
    /* 失败态由 refresh 体现：开关保持真实状态 */
  }
  await refresh();
}

function toggleTakeover() {
  if (!identity.canWrite) return;
  if (takeover.value) {
    takeoverPopOpen.value = true; // 开 → 关需二次确认
  } else {
    takeoverOn();
  }
}

async function confirmTakeoverOff() {
  if (!identity.canWrite) return;
  try {
    await controlApi.releaseFcs();
  } catch {
    /* 失败态由 refresh 体现 */
  }
  await refresh();
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

/** PWM 开关/滑杆写回后端：开=mode fixed（apply_tick 每 5s 写 pwm），关=auto 交还 BIOS */
async function pushZone(fan, patch) {
  if (!identity.canWrite) return false;
  try {
    await controlApi.updateFan(fan.id, patch);
    return true;
  } catch {
    return false; // 失败静默，下次 fetchFans 以后端状态为准
  }
}

async function togglePwm(fan) {
  if (!identity.canWrite) return;
  const next = !fan.pwm;
  fan.pwm = next; // 乐观更新
  // 开启时占空比下限 20%：抓到的当前值可能是 BIOS 闲置的 0%，钉 0 会停转风扇
  const fixed = next ? Math.max(fan.duty, 20) : undefined;
  if (next) fan.duty = fixed;
  const ok = await pushZone(fan, next ? { mode: 'fixed', fixed_pwm: fixed } : { mode: 'auto' });
  if (!ok) fan.pwm = !next;
}

async function onDutyCommit(fan) {
  if (!fan.pwm) return; // auto 模式下滑杆仅预览，不写
  // 提交钳制 ≥20%：滑杆物理上可拉到 0，钉 0 会把风扇停转（与开启时的下限一致）
  const fixed = Math.max(fan.duty, 20);
  if (fixed !== fan.duty) fan.duty = fixed;
  await pushZone(fan, { mode: 'fixed', fixed_pwm: fixed });
}

/** 重命名/删除气泡（按风区 id 记开合）；删除时后端自动把该通道交还 BIOS */
const popOpen = reactive({});
const renameValue = ref('');

async function confirmRename(fan) {
  if (!identity.canWrite) return;
  const name = renameValue.value.trim();
  if (!name || name === fan.name) return;
  const ok = await pushZone(fan, { name });
  if (ok) fan.name = name;
}

async function confirmDelete(fan) {
  if (!identity.canWrite) return;
  try {
    await controlApi.deleteFan(fan.id);
  } catch {
    /* 静默，列表刷新以实际为准 */
  }
  await refresh();
}

/** 转子驱动转速：优先传感器读数；无转速计通道按占空比估算（仅视觉，约 35%≈930RPM） */
function visualRpm(fan) {
  return fan.rpm > 0 ? fan.rpm : Math.round(fan.duty * 26.5);
}

/** 曲线编辑器（后端有曲线时回填，保存走 PUT /control/curves/{id}；缺省模板由适配层提供） */
const curvePts = ref([]);
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
  curvePts.value = (d.value.curveDefault ?? []).map((p) => [...p]);
  curveReadout.value = null;
  curveSaved.value = false;
}

/** 迟滞/斜率：跟随后端曲线回填，保存时一并提交 */
const curveHysteresis = ref(2);
const curveRamp = ref(5);
watch(
  () => d.value.curveMeta,
  (meta) => {
    if (meta) {
      curveHysteresis.value = meta.hysteresis_c ?? 2;
      curveRamp.value = meta.ramp_per_tick ?? 5;
    }
  },
  { immediate: true }
);

async function saveCurve() {
  curveSaved.value = false;
  if (!live.value || !identity.canWrite) return;
  savingCurve.value = true;
  try {
    let curveId = d.value.curveId;
    if (curveId == null) {
      // 首次保存：创建默认曲线后回填 id
      const created = await controlApi.createCurve({
        name: '默认曲线',
        points: curvePts.value,
        hysteresis_c: curveHysteresis.value,
        ramp_per_tick: curveRamp.value,
      });
      curveId = created.id;
    } else {
      await controlApi.updateCurve(curveId, {
        name: '默认曲线',
        points: curvePts.value,
        hysteresis_c: curveHysteresis.value,
        ramp_per_tick: curveRamp.value,
      });
    }
    curveSaved.value = true;
    refresh();
  } catch {
    /* 校验失败（1002）静默，气泡读数可自查 */
  } finally {
    savingCurve.value = false;
  }
}

/** 2s 轮询：转子/调速卡跟随传感器实时转速（页头开关可暂停）。
 * nas 路由全部 keep-alive：定时器须随 activated/deactivated 启停，
 * 挂在 onBeforeUnmount 在 keep-alive 下永远不会执行（离开页面仍在打接口） */
const autoRefresh = ref(true);
let pollTimer = null;

function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    if (autoRefresh.value) refresh();
  }, 2000);
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

onMounted(startPoll);
onBeforeUnmount(stopPoll);
onActivated(startPoll);
onDeactivated(stopPoll);

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
      :updated="lastUpdated"
    >
      <template #right>
        <label class="switch" :class="{ on: autoRefresh }" @click="autoRefresh = !autoRefresh">
          <span class="tr" />2s
        </label>
      </template>
    </u-page-header>

    <!-- 接管总开关（权限铁律：设置类仅管理员，非管理员整块隐藏） -->
    <div v-if="identity.canWrite" class="wg">
      <div class="wg-b opcard" style="padding: 14px 16px">
        <label
          class="switch"
          :class="{ on: takeover, disabled: !identity.canWrite }"
          :title="identity.deniedText"
          @click="toggleTakeover"
        >
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
              <button
                class="btn sm"
                :disabled="!takeover || !identity.canWrite"
                :title="identity.deniedText"
              >
                停用接管
              </button>
            </template>
            确认停用风扇接管？将交还主板 BIOS 控制（FCS 恢复）。
          </u-pop>
        </div>
      </div>
    </div>

    <!-- 硬件检测：未建风区的 pwm 通道（仅管理员） -->
    <div v-if="live && identity.canWrite && d.channels?.length" class="wg">
      <div class="wg-b opcard" style="padding: 14px 16px">
        <div class="ot" style="flex: 1">
          <b>硬件检测 · {{ d.channels.length }} 个未配置通道</b>
          <small
            >检测到主板 Super I/O 的 pwm 通道。添加风区后即可在此监控转速；mode=auto
            只读不干预，调速随时可在下方卡片开启</small
          >
        </div>
      </div>
      <div class="wg-b" style="padding-top: 0">
        <table class="u">
          <thead>
            <tr>
              <th>芯片</th>
              <th>通道</th>
              <th>占空比</th>
              <th>转速</th>
              <th>回路</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ch in d.channels" :key="detectKey(ch)">
              <td>{{ ch.chip }}</td>
              <td class="num">
                pwm{{ ch.pwm_channel }}{{ ch.fan_channel ? ` / fan${ch.fan_channel}` : '' }}
              </td>
              <td class="num">{{ Math.round(ch.current_pwm_pct ?? 0) }}%</td>
              <td class="num">
                {{ ch.current_rpm != null ? `${ch.current_rpm} RPM` : '—'
                }}<template v-if="ch.current_rpm"> ●</template>
              </td>
              <td>
                <select v-model="loopOf[detectKey(ch)]" style="width: auto">
                  <option value="chassis">机箱</option>
                  <option value="cpu">CPU</option>
                </select>
              </td>
              <td class="r">
                <button
                  class="btn sm"
                  :disabled="addingKey === detectKey(ch) || !identity.canWrite"
                  :title="identity.deniedText"
                  @click="addZone(ch)"
                >
                  {{ addingKey === detectKey(ch) ? '添加中…' : '添加风区' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 手动调速卡 -->
    <div class="grid">
      <div v-if="live && !cards.length" class="wg t12">
        <div class="wg-b small muted" style="padding: 22px 0; text-align: center">
          {{
            identity.canWrite
              ? '尚未添加风区 · 从上方「硬件检测」把在转的风扇添加为风区后，此处显示实时调速卡'
              : '管理员尚未配置风扇风区 · 配置后此处显示实时转速'
          }}
        </div>
      </div>
      <div v-for="fan in cards" :key="fan.name" class="wg t4 fan-card">
        <div class="wg-h">
          <u-icon name="fan" />
          <h3>{{ fan.name }}</h3>
          <span v-if="identity.canWrite" class="x">
            <u-pop
              v-model="popOpen[`ren:${fan.id}`]"
              ok-text="保存"
              cancel-text="取消"
              @confirm="confirmRename(fan)"
            >
              <template #trigger>
                <button
                  class="btn sm"
                  :disabled="!identity.canWrite"
                  :title="identity.deniedText"
                  @click="renameValue = fan.name"
                >
                  重命名
                </button>
              </template>
              <input
                v-model="renameValue"
                type="text"
                style="width: 170px"
                maxlength="64"
                placeholder="风区名称"
              />
            </u-pop>
            <u-pop
              v-model="popOpen[`del:${fan.id}`]"
              ok-text="删除"
              cancel-text="取消"
              danger
              @confirm="confirmDelete(fan)"
            >
              <template #trigger>
                <button class="btn sm" :disabled="!identity.canWrite" :title="identity.deniedText">
                  删除
                </button>
              </template>
              删除风区「{{ fan.name }}」？删除后立即交还主板控制。
            </u-pop>
          </span>
        </div>
        <div class="wg-b">
          <div class="fanrow">
            <fan-rotor size="lg" :rpm="visualRpm(fan)" />
            <span class="big num">{{ fan.rpm }}<small> RPM</small></span>
            <span class="num">占空比 {{ fan.duty }}%</span>
          </div>
          <input
            v-if="identity.canWrite"
            v-model.number="fan.duty"
            type="range"
            min="0"
            max="100"
            :disabled="!takeover"
            @change="onDutyCommit(fan)"
          />
          <div class="dutyrow">
            <label
              v-if="identity.canWrite"
              class="switch"
              :class="{ on: fan.pwm }"
              @click="togglePwm(fan)"
            >
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
            <template v-if="identity.canWrite">
              <button class="btn sm" @click="curveAdd"><u-icon name="plus" />添加点</button>
              <button class="btn sm" @click="curveReset">重置</button>
            </template>
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
          <div class="small" style="margin-bottom: 8px; font-weight: 600">
            {{ d.curveMeta?.name ?? '默认曲线（首次保存时创建）' }}
          </div>
          <div class="frm">
            <label>迟滞 °C</label>
            <input v-model.number="curveHysteresis" type="number" min="0" max="10" />
            <label>每 tick 斜率 %</label>
            <input v-model.number="curveRamp" type="number" min="1" max="50" />
          </div>
          <button
            v-if="identity.canWrite"
            class="btn pri"
            style="margin-top: 15px"
            :disabled="savingCurve || !live"
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
