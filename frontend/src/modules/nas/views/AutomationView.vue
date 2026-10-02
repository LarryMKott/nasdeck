<script setup>
/** 控制与自动化：活动告警 / 告警规则与通知 / 报告导出 三个页内页签 + 事件历史弹窗 */
import { computed, ref } from 'vue';
import { apiBase, apiData } from '../api/client';
import { useViewData } from '../composables/useViewData';
import { useIdentityStore } from '../stores/identity';
import * as nasData from '../api/data';
import UPageHeader from '../components/UPageHeader.vue';
import UModal from '../components/UModal.vue';
import UPop from '../components/UPop.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasAutomation' });

// 权限铁律：设置类操作仅管理员；非管理员不渲染规则表单/测试通知/报告导出（写操作）
const identity = useIdentityStore();
identity.ensure();

/** 页内页签：t1 活动告警 | t2 告警规则与通知 | t3 报告导出 */
const activeTab = ref('t1');

// 初始空骨架；mock 仅由适配层在后端不可达时整页演示回退
const { data: d, live, lastUpdated } = useViewData(nasData.fetchAutomation, {
  activeAlerts: [],
  recentEvents: [],
  channels: [],
});
const alerts = computed(() => d.value.activeAlerts ?? []);

/** 报告导出：真实生成 HTML 健康报告并触发下载 */
const exporting = ref(false);
const exportFailed = ref(false);
async function exportReport() {
  if (!identity.canWrite || exporting.value) return;
  exporting.value = true;
  exportFailed.value = false;
  try {
    const result = await apiData('/api/v1/report/health?redact=true', {
      method: 'POST',
      timeout: 60000,
    });
    // 后端返回根相对路径 /api/v1/...，FPK 形态须经 index.cgi 前缀才能命中（契约 §7.1）
    window.open(apiBase() + result.url, '_blank');
  } catch {
    exportFailed.value = true; // 失败可见，不静默
  } finally {
    exporting.value = false;
  }
}

/** 告警规则：表单值 + 保存（POST /alert/rules）。选项值直接用后端 metric/comparator 枚举，
 * 不做中文名→键映射（映射断链会静默提交错规则） */
const METRICS = [
  { value: 'temp_max', label: '温度' },
  { value: 'disk_failed', label: 'SMART 属性' },
  { value: 'cpu_percent', label: '负载' },
];
const ruleForm = ref({ metric: 'temp_max', comparator: '>', threshold: 60, duration: 60 });
const ruleSaving = ref(false);
const ruleSaved = ref(false);

async function saveRule() {
  if (!identity.canWrite) return;
  ruleSaving.value = true;
  ruleSaved.value = false;
  try {
    await apiData('/api/v1/alert/rules', {
      method: 'POST',
      body: {
        name: `规则 · ${METRICS.find((m) => m.value === ruleForm.value.metric)?.label ?? ruleForm.value.metric}`,
        metric: ruleForm.value.metric,
        comparator: ruleForm.value.comparator,
        threshold: Number(ruleForm.value.threshold) || 60,
        duration_ticks: parseInt(String(ruleForm.value.duration), 10) || 60,
        severity: 'warning',
        channel_ids: [],
        enabled: true,
      },
    });
    ruleSaved.value = true;
  } catch {
    /* 2000 校验失败静默，按钮态回落体现 */
  } finally {
    ruleSaving.value = false;
  }
}

/** 发送测试通知：POST /alert/channels/{id}/test（需已配置通知渠道） */
const testState = ref(''); // '' | 'sending' | 'ok' | 'fail'
async function sendTestNotice() {
  if (!identity.canWrite || testState.value === 'sending') return;
  const channel = d.value.channels?.[0];
  if (!channel) return;
  testState.value = 'sending';
  try {
    const result = await apiData(`/api/v1/alert/channels/${channel.id}/test`, { method: 'POST' });
    testState.value = result?.success ? 'ok' : 'fail';
  } catch {
    testState.value = 'fail';
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
            <label>持续时间</label>
            <input v-model="ruleForm.duration" type="text" />
            <label />
            <span>
              <button
                v-if="d.channels?.length"
                class="btn sm"
                :disabled="testState === 'sending'"
                @click="sendTestNotice"
              >
                <u-icon name="send" />{{
                  testState === 'sending'
                    ? '发送中…'
                    : testState === 'ok'
                      ? '已送达'
                      : testState === 'fail'
                        ? '发送失败'
                        : `发送测试通知（${d.channels[0].name}）`
                }}
              </button>
              <span v-else class="small muted">尚未配置通知渠道，保存规则后到渠道配置添加</span>
            </span>
          </div>
          <button
            v-if="identity.canWrite"
            class="btn pri"
            style="margin-top: 15px"
            :disabled="ruleSaving"
            @click="saveRule"
          >
            <u-icon name="check" />{{ ruleSaving ? '保存中…' : ruleSaved ? '已保存' : '保存规则' }}
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
        <u-pop
          ok-text="清空"
          cancel-text="取消"
          danger
          @confirm="logsCleared = true"
        >
          <template #trigger>
            <button class="btn sm">清空显示</button>
          </template>
          清空后仅影响本页显示，重新打开页面即恢复（事件记录存于后端）。
        </u-pop>
        <button class="btn sm pri" @click="logOpen = false">关闭</button>
      </div>
    </u-modal>
  </section>
</template>
