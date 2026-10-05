<script setup>
/** 控制与自动化：活动告警 / 告警规则与通知（渠道管理+多渠道推送）/ 报告导出 三个页内页签 + 事件历史弹窗 */
import { computed, reactive, ref, watch } from 'vue';
import { apiBase } from '../api/client';
import { exportHealthReport } from '../api/endpoints/report';
import {
  createChannel,
  createRule,
  deleteChannel,
  deleteRule,
  testChannel,
  updateChannel,
  updateRule,
} from '../api/endpoints/alert';
import { putSelftestSchedule } from '../api/endpoints/system';
import { useViewData } from '../composables/useViewData';
import { useIdentityStore } from '../stores/identity';
import { fetchAutomation } from '../services/automation';
import UPageHeader from '../components/UPageHeader.vue';
import UModal from '../components/UModal.vue';
import UPop from '../components/UPop.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasAutomation' });

// 权限铁律：设置类操作仅管理员；非管理员不渲染规则表单/渠道管理/报告导出（写操作）
const identity = useIdentityStore();
identity.ensure();

/** 页内页签：t1 活动告警 | t2 告警规则与通知 | t3 报告导出 */
const activeTab = ref('t1');

// 初始空骨架；mock 仅由适配层在后端不可达时整页演示回退
const {
  data: d,
  live,
  refresh,
  lastUpdated,
} = useViewData(fetchAutomation, {
  activeAlerts: [],
  recentEvents: [],
  channels: [],
  rules: [],
  selftestSchedule: { enabled: false, weekday: 6, hour: 4, type: 'short', last_run: null },
});
const alerts = computed(() => d.value.activeAlerts ?? []);

// ---- SMART 周期巡检计划（仅管理员；PUT 后由后台 10 分钟拍调度） ----
const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const schedForm = reactive({ enabled: false, weekday: 6, hour: 4, type: 'short' });
const schedLoaded = ref(false);
const schedSaving = ref(false);
const schedSaved = ref(false);

// 后端值到达后同步表单（仅一次；此后表单为编辑态，刷新才重置）
watch(
  () => d.value.selftestSchedule,
  (s) => {
    if (s && !schedLoaded.value) {
      Object.assign(schedForm, {
        enabled: !!s.enabled,
        weekday: s.weekday,
        hour: s.hour,
        type: s.type,
      });
      schedLoaded.value = true;
    }
  },
  { immediate: true }
);

async function saveSchedule() {
  if (!identity.canWrite || schedSaving.value) return;
  schedSaving.value = true;
  schedSaved.value = false;
  try {
    await putSelftestSchedule({ ...schedForm });
    schedSaved.value = true;
    await refresh();
  } catch {
    /* 失败静默刷新以实际为准 */
  } finally {
    schedSaving.value = false;
  }
}

/** 报告导出：真实生成 HTML 健康报告并触发下载 */
const exporting = ref(false);
const exportFailed = ref(false);
async function exportReport() {
  if (!identity.canWrite || exporting.value) return;
  exporting.value = true;
  exportFailed.value = false;
  try {
    const result = await exportHealthReport();
    // 后端返回根相对路径 /api/v1/...，FPK 形态须经 index.cgi 前缀才能命中（契约 §7.1）
    window.open(apiBase() + result.url, '_blank');
  } catch {
    exportFailed.value = true; // 失败可见，不静默
  } finally {
    exporting.value = false;
  }
}

/** 告警规则表单：选项值直接用后端 metric/comparator 枚举，不做中文名→键映射
 *（映射断链会静默提交错规则） */
const METRICS = [
  { value: 'temp_max', label: '温度' },
  { value: 'disk_failed', label: 'SMART 属性' },
  { value: 'cpu_percent', label: '负载' },
  // SMART 变化速率（smart_rate:<指标>）：7 天窗口增量按盘评估，threshold=最小增量
  { value: 'smart_rate:reallocated', label: 'SMART 重映射增速（7 天）' },
  { value: 'smart_rate:pending', label: 'SMART 待定扇区增速（7 天）' },
  { value: 'smart_rate:uncorrectable', label: 'SMART 不可修正增速（7 天）' },
  // 容量预测：threshold=写满剩余天数（days_to_full 低于阈值即告警）
  { value: 'capacity_forecast', label: '容量写满剩余天数（低于）' },
];
const METRIC_LABELS = {
  cpu_percent: '负载',
  mem_percent: '内存',
  temp_max: '温度',
  disk_temp: '盘温',
  disk_failed: 'SMART',
  raid_degraded: '阵列',
  'smart_rate:reallocated': '重映射增速',
  'smart_rate:pending': '待定扇区增速',
  'smart_rate:uncorrectable': '不可修正增速',
  capacity_forecast: '写满剩余天数',
};
const ruleForm = ref({ metric: 'temp_max', comparator: '>', threshold: 60, duration: 12 });
const ruleSaving = ref(false);
const ruleSaved = ref(false);

/** 推送渠道多选（chips）：一规则可同时推多个渠道，引擎逐渠道分发 */
const ruleChannels = ref([]);
function toggleRuleChannel(id) {
  const i = ruleChannels.value.indexOf(id);
  if (i >= 0) ruleChannels.value.splice(i, 1);
  else ruleChannels.value.push(id);
}

/** 剧本动作多选（M2.1 IF-THEN）：通知由渠道多选承载，这里是触发后的额外动作 */
const RULE_ACTIONS = [
  { value: 'fan_full', label: '风扇全速 15 分钟' },
  { value: 'report', label: '生成诊断报告' },
];
const ruleActions = ref([]);
function toggleRuleAction(value) {
  const i = ruleActions.value.indexOf(value);
  if (i >= 0) ruleActions.value.splice(i, 1);
  else ruleActions.value.push(value);
}

function actionsText(actions) {
  return (
    (actions ?? []).map((a) => RULE_ACTIONS.find((x) => x.value === a)?.label ?? a).join('、') ||
    '—'
  );
}

async function saveRule() {
  if (!identity.canWrite) return;
  ruleSaving.value = true;
  ruleSaved.value = false;
  try {
    await createRule({
      name: `规则 · ${METRICS.find((m) => m.value === ruleForm.value.metric)?.label ?? ruleForm.value.metric}`,
      metric: ruleForm.value.metric,
      comparator: ruleForm.value.comparator,
      threshold: Number(ruleForm.value.threshold) || 60,
      duration_ticks: parseInt(String(ruleForm.value.duration), 10) || 12,
      severity: 'warning',
      channel_ids: [...ruleChannels.value],
      actions: [...ruleActions.value],
      enabled: true,
    });
    ruleSaved.value = true;
    refresh(); // 规则列表回显（含刚保存的多渠道选择）
  } catch {
    /* 2000 校验失败静默，按钮态回落体现 */
  } finally {
    ruleSaving.value = false;
  }
}

/** 规则列表：条件可读化（阈值规则 tick 为 5s 调速轮；smart_rate/capacity 为 15 分钟采集轮） */
function condText(r) {
  if (r.metric?.startsWith('smart_rate:') || r.metric === 'capacity_forecast') {
    return `${METRIC_LABELS[r.metric] ?? r.metric} ${r.comparator} ${r.threshold} · 连续 ${r.duration_ticks} 轮（15 分钟/轮）`;
  }
  return `${METRIC_LABELS[r.metric] ?? r.metric} ${r.comparator} ${r.threshold} · 持续 ${r.duration_ticks * 5}s`;
}

function channelNames(ids) {
  return (
    (ids ?? [])
      .map((id) => d.value.channels?.find((c) => c.id === id)?.name)
      .filter(Boolean)
      .join('、') || '—'
  );
}

function hasDeletedChannel(ids) {
  return (ids ?? []).some((id) => !d.value.channels?.some((c) => c.id === id));
}

/** 规则启停：PUT 全量更新（未提及字段按后端默认重置，必须整份带上） */
async function toggleRule(r) {
  if (!identity.canWrite) return;
  const next = !r.enabled;
  const prev = r.enabled;
  r.enabled = next;
  try {
    await updateRule(r.id, {
      name: r.name,
      metric: r.metric,
      comparator: r.comparator,
      threshold: r.threshold,
      duration_ticks: r.duration_ticks,
      severity: r.severity,
      channel_ids: [...(r.channel_ids ?? [])],
      actions: [...(r.actions ?? [])],
      enabled: next,
    });
  } catch {
    r.enabled = prev;
  }
}

async function deleteRuleRow(r) {
  try {
    await deleteRule(r.id);
  } catch {
    /* 静默，刷新以实际为准 */
  }
  refresh();
}

/** 通知渠道类型与各类型配置字段（与后端 channels/*.required_fields 对齐；
 * secret 字段以 password 框呈现，编辑时回显掩码串，原样保存=保留旧凭据） */
const CHANNEL_TYPES = [
  {
    value: 'telegram',
    label: 'Telegram',
    fields: [
      { key: 'bot_token', label: 'Bot Token', secret: true, required: true },
      { key: 'chat_id', label: 'Chat ID', required: true },
    ],
  },
  {
    value: 'bark',
    label: 'Bark (iOS)',
    fields: [
      { key: 'device_key', label: 'Device Key', secret: true, required: true },
      { key: 'server', label: '自建服务器（可选）', placeholder: 'https://api.day.app' },
    ],
  },
  {
    value: 'email',
    label: '邮件 SMTP',
    fields: [
      { key: 'host', label: 'SMTP 服务器', required: true, placeholder: 'smtp.example.com' },
      { key: 'port', label: '端口', required: true, placeholder: '587' },
      { key: 'username', label: '账号', required: true },
      { key: 'password', label: '密码 / 授权码', secret: true, required: true },
      { key: 'to', label: '收件邮箱', required: true },
    ],
  },
  {
    value: 'webhook',
    label: 'Webhook',
    fields: [{ key: 'url', label: 'URL', required: true, placeholder: 'https://example.com/hook' }],
  },
];
const TYPE_LABELS = Object.fromEntries(CHANNEL_TYPES.map((t) => [t.value, t.label]));
const typeMeta = computed(() => CHANNEL_TYPES.find((t) => t.value === chanForm.value.type));

function configSummary(cfg) {
  return (
    Object.values(cfg ?? {})
      .filter((v) => v !== '' && v != null)
      .join(' · ') || '—'
  );
}

/** 渠道编辑弹窗：新建空表单 / 编辑回填脱敏配置（掩码串原样回传，后端合并旧凭据） */
const chanModalOpen = ref(false);
const chanSaving = ref(false);
const chanForm = ref({ id: null, name: '', type: 'bark', enabled: true, config: {} });

function openChannelCreate() {
  chanForm.value = { id: null, name: '', type: 'bark', enabled: true, config: {} };
  chanModalOpen.value = true;
}

function openChannelEdit(c) {
  chanForm.value = {
    id: c.id,
    name: c.name,
    type: c.type,
    enabled: c.enabled,
    config: { ...c.config_masked },
  };
  chanModalOpen.value = true;
}

/** 切换类型：各类型配置字段不同，清空避免残留其它类型的键 */
function onChanTypeChange() {
  chanForm.value.config = {};
}

async function saveChannel() {
  if (!identity.canWrite || chanSaving.value) return;
  const f = chanForm.value;
  if (!f.name.trim()) return;
  chanSaving.value = true;
  try {
    const body = { name: f.name.trim(), type: f.type, config: { ...f.config }, enabled: f.enabled };
    if (f.id == null) await createChannel(body);
    else await updateChannel(f.id, body);
    chanModalOpen.value = false;
    refresh();
  } catch {
    /* 校验失败（缺字段 / url 非法 → 1002）静默，弹窗留在原地可改 */
  } finally {
    chanSaving.value = false;
  }
}

/** 渠道启停：掩码配置原样回传（后端合并旧凭据） */
async function toggleChannel(c) {
  if (!identity.canWrite) return;
  const next = !c.enabled;
  const prev = c.enabled;
  c.enabled = next;
  try {
    await updateChannel(c.id, {
      name: c.name,
      type: c.type,
      config: { ...c.config_masked },
      enabled: next,
    });
  } catch {
    c.enabled = prev;
  }
}

async function deleteChan(c) {
  try {
    await deleteChannel(c.id);
  } catch {
    /* 静默，刷新以实际为准 */
  }
  refresh();
}

/** 渠道连通性测试：逐渠道行内按钮（发送真实测试通知） */
const chanTestState = reactive({});
async function testChan(c) {
  if (!identity.canWrite || chanTestState[c.id] === 'sending') return;
  chanTestState[c.id] = 'sending';
  try {
    const result = await testChannel(c.id);
    chanTestState[c.id] = result?.success ? 'ok' : 'fail';
  } catch {
    chanTestState[c.id] = 'fail';
  }
}

const logOpen = ref(false);
const logsCleared = ref(false);

/** 弹窗数据源 = 真实告警事件流（后端无独立日志接口） */
const eventLogs = computed(() =>
  logsCleared.value
    ? []
    : (d.value.recentEvents ?? []).map((e) => ({
        time: e.time,
        level: e.severity === 'critical' ? 'bad' : e.severity === 'warning' ? 'warn' : '',
        text: `${e.status === 'firing' ? 'FIRE' : e.status?.toUpperCase()}  ${e.message || e.rule_name}`,
      }))
);

const headerTag = computed(() => ({
  type: alerts.value.length ? 'warn' : 'ok',
  text: live.value ? `${alerts.value.length} 条活动告警` : '演示数据',
}));
</script>

<template>
  <section>
    <u-page-header
      title="控制与自动化"
      sub="告警 · 通知 · 报告"
      :tag="headerTag"
      :updated="lastUpdated"
    />

    <div class="wg">
      <div class="wg-b" style="padding-bottom: 0">
        <div class="tabs2">
          <button :class="{ on: activeTab === 't1' }" @click="activeTab = 't1'">活动告警</button>
          <button :class="{ on: activeTab === 't2' }" @click="activeTab = 't2'">
            告警规则与通知
          </button>
          <button :class="{ on: activeTab === 't3' }" @click="activeTab = 't3'">报告导出</button>
        </div>

        <!-- 活动告警 -->
        <div v-if="activeTab === 't1'" style="padding: 15px 0">
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
          <div v-if="!alerts.length" class="small muted" style="padding: 8px 0">
            {{ live ? '当前无活动告警' : '后端不可达，显示演示告警' }}
          </div>
        </div>

        <!-- 告警规则与通知：设置类操作仅管理员，非管理员整块不渲染 -->
        <div v-else-if="activeTab === 't2' && identity.canWrite" style="padding: 15px 0">
          <!-- 通知渠道管理 -->
          <div class="small" style="margin-bottom: 8px; font-weight: 600">通知渠道</div>
          <table v-if="d.channels?.length" class="u" style="margin-bottom: 10px">
            <thead>
              <tr>
                <th>名称</th>
                <th>类型</th>
                <th>配置</th>
                <th>启用</th>
                <th class="r">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in d.channels" :key="c.id">
                <td>{{ c.name }}</td>
                <td class="small">{{ TYPE_LABELS[c.type] ?? c.type }}</td>
                <td
                  class="small muted num"
                  style="
                    max-width: 280px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                  "
                  :title="configSummary(c.config_masked)"
                >
                  {{ configSummary(c.config_masked) }}
                </td>
                <td>
                  <label class="switch" :class="{ on: c.enabled }" @click="toggleChannel(c)">
                    <span class="tr" />
                  </label>
                </td>
                <td class="r" style="white-space: nowrap">
                  <button
                    class="btn sm"
                    :disabled="chanTestState[c.id] === 'sending'"
                    :title="`发送测试通知到「${c.name}」`"
                    @click="testChan(c)"
                  >
                    <u-icon name="send" />{{
                      chanTestState[c.id] === 'sending'
                        ? '发送中'
                        : chanTestState[c.id] === 'ok'
                          ? '已送达'
                          : chanTestState[c.id] === 'fail'
                            ? '失败'
                            : '测试'
                    }}
                  </button>
                  <button class="btn sm" @click="openChannelEdit(c)">编辑</button>
                  <u-pop ok-text="删除" cancel-text="取消" danger @confirm="deleteChan(c)">
                    <template #trigger>
                      <button class="btn sm">删除</button>
                    </template>
                    删除渠道「{{ c.name }}」？引用它的规则将不再经它推送。
                  </u-pop>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="small muted" style="margin-bottom: 10px">
            尚未配置通知渠道——先添加一个（Telegram / Bark / 邮件 /
            Webhook），才能在规则中勾选推送目标
          </div>
          <button class="btn sm" @click="openChannelCreate"><u-icon name="plus" />添加渠道</button>

          <!-- 告警规则表单 -->
          <div class="small" style="margin: 18px 0 8px; font-weight: 600">告警规则</div>
          <div class="frm">
            <label>监控指标</label>
            <select v-model="ruleForm.metric">
              <option v-for="m in METRICS" :key="m.value" :value="m.value">{{ m.label }}</option>
            </select>
            <label>比较</label>
            <select v-model="ruleForm.comparator">
              <option value=">">&gt; 高于</option>
              <option value="<">&lt; 低于</option>
            </select>
            <label>阈值</label>
            <input v-model="ruleForm.threshold" type="text" />
            <label>持续时间（轮 ×5s）</label>
            <input v-model="ruleForm.duration" type="text" />
            <label>通知渠道（可多选）</label>
            <span v-if="d.channels?.length" class="chips" style="align-self: center">
              <button
                v-for="c in d.channels"
                :key="c.id"
                type="button"
                :class="{ on: ruleChannels.includes(c.id) }"
                @click="toggleRuleChannel(c.id)"
              >
                {{ c.name }}
              </button>
            </span>
            <span v-else class="small muted" style="align-self: center">
              暂无渠道可推——先在上方「添加渠道」
            </span>
            <label>触发后动作（可多选）</label>
            <span class="chips" style="align-self: center">
              <button
                v-for="a in RULE_ACTIONS"
                :key="a.value"
                type="button"
                :class="{ on: ruleActions.includes(a.value) }"
                @click="toggleRuleAction(a.value)"
              >
                {{ a.label }}
              </button>
            </span>
          </div>
          <button class="btn pri" style="margin-top: 15px" :disabled="ruleSaving" @click="saveRule">
            <u-icon name="check" />{{ ruleSaving ? '保存中…' : ruleSaved ? '已保存' : '保存规则' }}
          </button>

          <!-- 已有规则列表 -->
          <table v-if="d.rules?.length" class="u" style="margin-top: 15px">
            <thead>
              <tr>
                <th>规则</th>
                <th>条件</th>
                <th>通知渠道</th>
                <th>动作</th>
                <th>启用</th>
                <th class="r">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in d.rules" :key="r.id">
                <td>{{ r.name }}</td>
                <td class="num small">{{ condText(r) }}</td>
                <td class="small">
                  {{ channelNames(r.channel_ids) }}
                  <span v-if="hasDeletedChannel(r.channel_ids)" class="muted">（含已删渠道）</span>
                </td>
                <td class="small">{{ actionsText(r.actions) }}</td>
                <td>
                  <label class="switch" :class="{ on: r.enabled }" @click="toggleRule(r)">
                    <span class="tr" />
                  </label>
                </td>
                <td class="r">
                  <u-pop ok-text="删除" cancel-text="取消" danger @confirm="deleteRuleRow(r)">
                    <template #trigger>
                      <button class="btn sm">删除</button>
                    </template>
                    删除规则「{{ r.name }}」？其活跃告警将自动收尾。
                  </u-pop>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="small muted" style="margin-top: 15px">
            还没有规则——上方表单保存后在此列出，触发时按勾选渠道推送
          </div>

          <!-- SMART 周期巡检计划 -->
          <div class="small" style="margin: 22px 0 8px; font-weight: 600">SMART 周期巡检</div>
          <div class="frm">
            <label>启用巡检</label>
            <label
              class="switch"
              :class="{ on: schedForm.enabled }"
              @click="schedForm.enabled = !schedForm.enabled"
            >
              <span class="tr" />
            </label>
            <label>执行时间</label>
            <div style="display: flex; gap: 8px">
              <select v-model="schedForm.weekday" style="width: auto">
                <option v-for="(w, i) in WEEKDAYS" :key="w" :value="i">{{ w }}</option>
              </select>
              <select v-model="schedForm.hour" style="width: auto">
                <option v-for="h in 24" :key="h - 1" :value="h - 1">
                  {{ `${h - 1}`.padStart(2, '0') }} 时
                </option>
              </select>
            </div>
            <label>自检类型</label>
            <select v-model="schedForm.type">
              <option value="short">短自检（约 2 分钟/盘）</option>
              <option value="long">长自检（约 4 小时/盘）</option>
            </select>
          </div>
          <div class="small muted" style="margin-top: 9px">
            每周{{ WEEKDAYS[schedForm.weekday] }}
            {{ `${schedForm.hour}`.padStart(2, '0') }} 点后逐盘串行自检；
            结果写入事件历史，异常盘向全部启用渠道告警。休眠盘会被唤醒（smartctl -t）。
            <template v-if="d.selftestSchedule?.last_run"
              >上次运行：{{ d.selftestSchedule.last_run }}。</template
            >
          </div>
          <button
            class="btn pri"
            style="margin-top: 12px"
            :disabled="schedSaving"
            @click="saveSchedule"
          >
            <u-icon name="check" />{{
              schedSaving ? '保存中…' : schedSaved ? '已保存' : '保存巡检计划'
            }}
          </button>
        </div>
        <div v-else-if="activeTab === 't2'" class="small muted" style="padding: 15px 0">
          告警规则为管理员设置项 · 如需调整请联系管理员
        </div>

        <!-- 报告导出 -->
        <div v-else style="padding: 15px 0">
          <div class="frm">
            <label>健康报告</label>
            <span class="small" style="align-self: center">
              生成当前系统的脱敏 HTML 健康报告并下载
            </span>
            <label />
            <span v-if="identity.canWrite">
              <button class="btn" :disabled="exporting" @click="exportReport">
                <u-icon name="dl" />{{ exporting ? '生成中…' : '立即导出' }}
              </button>
              <span v-if="exportFailed" class="small" style="margin-left: 8px; color: var(--bad)">
                生成失败，请稍后重试
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 事件历史 -->
    <div class="wg" style="margin-bottom: 0">
      <div class="wg-h">
        <u-icon name="hist" />
        <h3>事件历史</h3>
        <span class="x">
          <button class="btn sm" @click="logOpen = true">查看事件流</button>
        </span>
      </div>
      <div class="wg-b small muted">最近告警事件的触发与恢复记录（来自告警引擎）</div>
    </div>

    <!-- 事件历史弹窗 -->
    <u-modal v-model="logOpen" title="事件历史" icon="hist">
      <div class="logbox num">
        <template v-if="eventLogs.length">
          <div
            v-for="(log, i) in eventLogs"
            :key="i"
            class="log-line"
            :class="log.level === 'warn' ? 'lv-warn' : log.level === 'bad' ? 'lv-bad' : ''"
          >
            <span class="lt">{{ log.time }}</span
            >{{ log.text }}
          </div>
        </template>
        <div v-else class="log-line muted">
          {{ logsCleared ? '记录已清空（仅本次会话）' : '暂无告警事件' }}
        </div>
      </div>
      <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px">
        <u-pop ok-text="清空" cancel-text="取消" danger @confirm="logsCleared = true">
          <template #trigger>
            <button class="btn sm">清空显示</button>
          </template>
          清空后仅影响本页显示，重新打开页面即恢复（事件记录存于后端）。
        </u-pop>
        <button class="btn sm pri" @click="logOpen = false">关闭</button>
      </div>
    </u-modal>

    <!-- 渠道编辑弹窗 -->
    <u-modal
      v-model="chanModalOpen"
      :title="chanForm.id == null ? '添加通知渠道' : `编辑渠道 · ${chanForm.name}`"
      icon="send"
    >
      <div class="frm">
        <label>名称</label>
        <input v-model="chanForm.name" type="text" maxlength="64" placeholder="如 手机 Bark" />
        <label>类型</label>
        <select v-model="chanForm.type" @change="onChanTypeChange">
          <option v-for="t in CHANNEL_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
        <template v-for="f in typeMeta?.fields ?? []" :key="f.key">
          <label>{{ f.label }}</label>
          <input
            v-model="chanForm.config[f.key]"
            :type="f.secret ? 'password' : 'text'"
            :placeholder="f.placeholder ?? ''"
            autocomplete="off"
            spellcheck="false"
          />
        </template>
        <label>启用</label>
        <label
          class="switch"
          :class="{ on: chanForm.enabled }"
          style="align-self: center"
          @click.prevent="chanForm.enabled = !chanForm.enabled"
        >
          <span class="tr" />
        </label>
      </div>
      <div class="small muted" style="margin-top: 10px">
        编辑时带 ****
        的掩码值原样保存即保留旧凭据；保存后点列表「测试」验证连通性。规则触发时按所选渠道逐个推送。
      </div>
      <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px">
        <button class="btn" @click="chanModalOpen = false">取消</button>
        <button class="btn pri" :disabled="chanSaving" @click="saveChannel">
          <u-icon name="check" />{{ chanSaving ? '保存中…' : '保存渠道' }}
        </button>
      </div>
    </u-modal>
  </section>
</template>
