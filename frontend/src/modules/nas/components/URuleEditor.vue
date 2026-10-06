<script setup>
/** 告警规则编辑器（共享组件）：阈值规则表单（含 SMART 增速/容量预测指标）+ 剧本动作
 * 多选 + 规则列表启停删除。AutomationView 与 SettingsView 共用——规则逻辑单源。
 * 数据由父组件拉取，写操作后 emit refresh 回拉。 */
import { ref } from 'vue';
import { createRule, deleteRule, updateRule } from '../api/endpoints/alert';
import UPop from './UPop.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

const props = defineProps({
  /** 规则清单（AlertRuleItem[]） */
  rules: { type: Array, default: () => [] },
  /** 渠道清单（规则 channel_ids 多选数据源） */
  channels: { type: Array, default: () => [] },
  canWrite: { type: Boolean, default: false },
});
const emit = defineEmits(['refresh']);

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
  if (!props.canWrite) return;
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
    emit('refresh'); // 规则列表回显（含刚保存的多渠道选择）
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
      .map((id) => props.channels?.find((c) => c.id === id)?.name)
      .filter(Boolean)
      .join('、') || '—'
  );
}

function hasDeletedChannel(ids) {
  return (ids ?? []).some((id) => !props.channels?.some((c) => c.id === id));
}

/** 规则启停：PUT 全量更新（未提及字段按后端默认重置，必须整份带上） */
async function toggleRule(r) {
  if (!props.canWrite) return;
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
  emit('refresh');
}
</script>

<template>
  <div>
    <div class="small" style="margin-bottom: 8px; font-weight: 600">告警规则</div>
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
      <span v-if="channels?.length" class="chips" style="align-self: center">
        <button
          v-for="c in channels"
          :key="c.id"
          type="button"
          :class="{ on: ruleChannels.includes(c.id) }"
          @click="toggleRuleChannel(c.id)"
        >
          {{ c.name }}
        </button>
      </span>
      <span v-else class="small muted" style="align-self: center">
        暂无渠道可推——先在上方「通知渠道」添加
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
    <table v-if="rules?.length" class="u" style="margin-top: 15px">
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
        <tr v-for="r in rules" :key="r.id">
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
  </div>
</template>
