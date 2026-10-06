<script setup>
/** 控制与自动化：活动告警 / 告警规则与通知（渠道管理+多渠道推送）/ 报告导出 三个页内页签 + 事件历史弹窗 */
import { computed, reactive, ref, watch } from 'vue';
import { apiBase } from '../api/client';
import { exportHealthReport } from '../api/endpoints/report';
import {
  exportConfigBackup,
  importConfigBackup,
  putReportSchedule,
  putSelftestSchedule,
  sendReportNow,
} from '../api/endpoints/system';
import { useViewData } from '../composables/useViewData';
import { useIdentityStore } from '../stores/identity';
import { fetchAutomation } from '../services/automation';
import UPageHeader from '../components/UPageHeader.vue';
import UChannelManager from '../components/UChannelManager.vue';
import UModal from '../components/UModal.vue';
import UPop from '../components/UPop.vue';
import URuleEditor from '../components/URuleEditor.vue';
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
  reportSchedule: { enabled: false, weekday: 0, hour: 9, last_run: null },
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

// ---- 配置备份/恢复（M3.5）：POST 动词语义仅管理员；导入 replace-all 有二次确认 ----
const backupFile = ref(null);
const backupBusy = ref(false);
const backupMsg = ref('');
const backupOk = ref(false);

async function downloadBackup() {
  if (!identity.canWrite || backupBusy.value) return;
  backupBusy.value = true;
  backupMsg.value = '';
  try {
    const data = await exportConfigBackup(true); // 本机归档：带明文凭据
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `nasdeck-config-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    backupMsg.value = '已下载备份文件（含渠道凭据明文，请妥善保管）';
    backupOk.value = true;
  } catch {
    backupMsg.value = '导出失败，请稍后重试';
    backupOk.value = false;
  } finally {
    backupBusy.value = false;
  }
}

// ---- 周报推送计划（M3.1）：调度为 10 分钟拍周去重；手动发送调试按钮 ----
const reportForm = reactive({ enabled: false, weekday: 0, hour: 9 });
const reportLoaded = ref(false);
const reportSending = ref(false);
const reportSaved = ref(false);
const reportSent = ref('');

watch(
  () => d.value.reportSchedule,
  (s) => {
    if (s && !reportLoaded.value) {
      Object.assign(reportForm, { enabled: !!s.enabled, weekday: s.weekday, hour: s.hour });
      reportLoaded.value = true;
    }
  },
  { immediate: true }
);

async function saveReportSchedule() {
  if (!identity.canWrite || reportSending.value) return;
  reportSending.value = true;
  reportSaved.value = false;
  try {
    await putReportSchedule({ ...reportForm });
    reportSaved.value = true;
    await refresh();
  } catch {
    /* 失败静默，刷新以实际为准 */
  } finally {
    reportSending.value = false;
  }
}

async function sendReportNowClick() {
  if (!identity.canWrite || reportSending.value) return;
  reportSending.value = true;
  try {
    const r = await sendReportNow();
    reportSent.value = r.digest;
  } catch {
    reportSent.value = '发送失败，请稍后重试';
  } finally {
    reportSending.value = false;
  }
}

async function restoreBackup() {
  if (!identity.canWrite || backupBusy.value || !backupFile.value) return;
  backupBusy.value = true;
  backupMsg.value = '';
  try {
    const text = await backupFile.value.text();
    const counts = await importConfigBackup(JSON.parse(text));
    backupMsg.value = `恢复完成：风扇 ${counts.fan_zones ?? 0} / 规则 ${counts.alert_rules ?? 0} / 渠道 ${counts.alert_channels ?? 0}（掩码备份的渠道需重填凭据）`;
    backupOk.value = true;
    await refresh();
  } catch {
    backupMsg.value = '恢复失败：文件格式不符或 schema 版本不支持';
    backupOk.value = false;
  } finally {
    backupBusy.value = false;
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
          <u-channel-manager
            :channels="d.channels"
            :can-write="identity.canWrite"
            @refresh="refresh"
          />

          <u-rule-editor
            :rules="d.rules"
            :channels="d.channels"
            :can-write="identity.canWrite"
            @refresh="refresh"
          />

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

          <!-- 周报推送计划 -->
          <div class="small" style="margin: 22px 0 8px; font-weight: 600">周报推送</div>
          <div class="frm">
            <label>启用推送</label>
            <label
              class="switch"
              :class="{ on: reportForm.enabled }"
              @click="reportForm.enabled = !reportForm.enabled"
            >
              <span class="tr" />
            </label>
            <label>推送时间</label>
            <div style="display: flex; gap: 8px">
              <select v-model="reportForm.weekday" style="width: auto">
                <option v-for="(w, i) in WEEKDAYS" :key="w" :value="i">{{ w }}</option>
              </select>
              <select v-model="reportForm.hour" style="width: auto">
                <option v-for="h in 24" :key="h - 1" :value="h - 1">
                  {{ `${h - 1}`.padStart(2, '0') }} 时
                </option>
              </select>
            </div>
          </div>
          <div class="small muted" style="margin-top: 9px">
            每周{{ WEEKDAYS[reportForm.weekday] }}
            {{ `${reportForm.hour}`.padStart(2, '0') }} 点汇总上周告警 / 最高温 / 容量预测 / SMART
            变化，向全部启用渠道推送。{{
              d.reportSchedule?.last_run ? `上次推送：${d.reportSchedule.last_run}。` : ''
            }}
          </div>
          <div style="display: flex; gap: 8px; margin-top: 12px">
            <button class="btn pri" :disabled="reportSending" @click="saveReportSchedule">
              <u-icon name="check" />{{
                reportSending ? '保存中…' : reportSaved ? '已保存' : '保存计划'
              }}
            </button>
            <button class="btn" :disabled="reportSending" @click="sendReportNowClick">
              <u-icon name="send" />立即发送
            </button>
          </div>
          <pre
            v-if="reportSent"
            class="small num"
            style="margin-top: 10px; color: var(--tx2); white-space: pre-wrap"
            >{{ reportSent }}</pre>

          <!-- 配置备份/恢复 -->
          <div class="small" style="margin: 22px 0 8px; font-weight: 600">配置备份与恢复</div>
          <div class="small muted" style="margin-bottom: 10px">
            整体导出风扇控区/曲线、告警规则/渠道、别名/白名单与巡检/静音计划为 JSON；恢复为
            <b>整体替换</b>（现配置将被备份文件覆盖）。导出含渠道凭据明文，请妥善保管。
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center">
            <button class="btn" :disabled="backupBusy" @click="downloadBackup">
              <u-icon name="dl" />导出配置
            </button>
            <input
              ref="backupFile"
              type="file"
              accept="application/json,.json"
              style="display: none"
              @change="backupFile = $event.target.files[0] || null"
            />
            <button class="btn" :disabled="backupBusy" @click="$refs.backupFile.click()">
              <u-icon name="layers" />选择备份文件
            </button>
            <u-pop ok-text="覆盖恢复" cancel-text="取消" danger @confirm="restoreBackup">
              <template #trigger>
                <button class="btn" :disabled="backupBusy || !backupFile">
                  <u-icon name="refresh" />恢复
                </button>
              </template>
              恢复将<b>整体替换</b>当前全部配置（风扇/告警/别名/计划），确认覆盖？
            </u-pop>
          </div>
          <div
            v-if="backupMsg"
            class="small"
            :class="backupOk ? 't-ok' : ''"
            style="margin-top: 9px"
          >
            {{ backupMsg }}
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
  </section>
</template>
