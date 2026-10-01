<script setup>
/** 控制与自动化：活动告警 / 告警规则与通知 / 报告导出 三个页内页签 + 日志弹窗（后端 + 演示回退） */
import { computed, ref } from 'vue';
import { automation as mockAutomation, activeAlerts as mockAlerts } from '../mock';
import { apiBase, apiData } from '../api/client';
import { useViewData } from '../composables/useViewData';
import { useIdentityStore } from '../stores/identity';
import * as nasData from '../api/data';
import UPageHeader from '../components/UPageHeader.vue';
import UModal from '../components/UModal.vue';
import UPop from '../components/UPop.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasAutomation' });

// 权限铁律：设置类操作仅管理员；非管理员禁用规则保存与报告导出
const identity = useIdentityStore();
identity.ensure();

/** 页内页签：t1 活动告警 | t2 告警规则与通知 | t3 报告导出 */
const activeTab = ref('t1');

const {
  data: d,
  live,
  lastUpdated,
} = useViewData(nasData.fetchAutomation, {
  ...mockAutomation,
  activeAlerts: mockAlerts,
});
const alerts = computed(() => d.value.activeAlerts ?? []);

/** 报告导出：真实生成 HTML 健康报告并触发下载 */
const exporting = ref(false);
async function exportReport() {
  if (!identity.canWrite) return;
  if (exporting.value) return;
  exporting.value = true;
  try {
    const result = await apiData('/api/v1/report/health?redact=true', {
      method: 'POST',
      timeout: 60000,
    });
    // 后端返回根相对路径 /api/v1/...，FPK 形态须经 index.cgi 前缀才能命中（契约 §7.1）
    window.open(apiBase() + result.url, '_blank');
  } catch {
    /* 后端不可达静默 */
  } finally {
    exporting.value = false;
  }
}

/** 通知渠道 / 导出格式 chips（可多选的 on 态） */
const channels = ref(['飞牛通知']);
const formats = ref(['MD', 'HTML']);

/** 告警规则：表单值 + 保存（POST /alert/rules） */
const ruleForm = ref({ ...d.value.alertRule });
const ruleSaving = ref(false);
const ruleSaved = ref(false);

async function saveRule() {
  if (!identity.canWrite) return;
  ruleSaving.value = true;
  ruleSaved.value = false;
  try {
    const metric =
      { 温度: 'temp_max', 'SMART 属性': 'disk_failed', 负载: 'cpu_percent' }[
        ruleForm.value.metric
      ] ?? 'temp_max';
    await apiData('/api/v1/alert/rules', {
      method: 'POST',
      body: {
        name: `规则 · ${ruleForm.value.metric}`,
        metric,
        comparator: '>',
        threshold: Number(ruleForm.value.threshold) || 60,
        duration_ticks: parseInt(String(ruleForm.value.duration), 10) || 60,
        severity: 'warning',
        channel_ids: [],
        enabled: true,
      },
    });
    ruleSaved.value = true;
  } catch {
    /* 2000 校验失败静默 */
  } finally {
    ruleSaving.value = false;
  }
}

const logOpen = ref(false);
const clearPopOpen = ref(false);
const logsCleared = ref(false);
const autoRefresh = ref(true);

const headerTag = computed(() => ({
  type: alerts.value.length ? 'warn' : 'ok',
  text: live.value ? `${alerts.value.length} 条活动告警` : '演示数据',
}));
</script>

<template>
  <section>
    <u-page-header
      title="控制与自动化"
      sub="告警 · 通知 · 报告 · 日志"
      :tag="headerTag"
      :updated="lastUpdated"
    >
      <template #right>
        <label class="switch" :class="{ on: autoRefresh }" @click="autoRefresh = !autoRefresh">
          <span class="tr" />15s
        </label>
      </template>
    </u-page-header>

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
        </div>

        <!-- 告警规则与通知 -->
        <div v-else-if="activeTab === 't2'" style="padding: 15px 0">
          <div class="frm">
            <label>监控指标</label>
            <select>
              <option>温度</option>
              <option>SMART 属性</option>
              <option>负载</option>
            </select>
            <label>比较</label>
            <select>
              <option>&gt; 高于</option>
              <option>&lt; 低于</option>
            </select>
            <label>阈值</label>
            <input v-model="ruleForm.threshold" type="text" />
            <label>持续时间</label>
            <input v-model="ruleForm.duration" type="text" />
            <label>通知渠道</label>
            <span class="chips">
              <button
                v-for="ch in ['飞牛通知', 'Webhook']"
                :key="ch"
                :class="{ on: channels.includes(ch) }"
                @click="
                  channels.includes(ch)
                    ? channels.splice(channels.indexOf(ch), 1)
                    : channels.push(ch)
                "
              >
                {{ ch }}
              </button>
            </span>
            <label />
            <span>
              <button class="btn sm"><u-icon name="send" />发送测试通知</button>
            </span>
          </div>
          <button
            class="btn pri"
            style="margin-top: 15px"
            :disabled="ruleSaving || !identity.canWrite"
            :title="identity.deniedText"
            @click="saveRule"
          >
            <u-icon name="check" />{{ ruleSaving ? '保存中…' : ruleSaved ? '已保存' : '保存规则' }}
          </button>
        </div>

        <!-- 报告导出 -->
        <div v-else style="padding: 15px 0">
          <div class="frm">
            <label>导出周期</label>
            <select>
              <option>{{ d.report.schedule }}</option>
              <option>每周一 08:00</option>
              <option>关闭</option>
            </select>
            <label>格式</label>
            <span class="chips">
              <button
                v-for="fmt in d.report.formats"
                :key="fmt"
                :class="{ on: formats.includes(fmt) }"
                @click="
                  formats.includes(fmt)
                    ? formats.splice(formats.indexOf(fmt), 1)
                    : formats.push(fmt)
                "
              >
                {{ fmt }}
              </button>
            </span>
            <label />
            <span>
              <button
                v-if="identity.canWrite"
                class="btn"
                :disabled="exporting"
                @click="exportReport"
              >
                <u-icon name="dl" />{{ exporting ? '生成中…' : '立即导出' }}
              </button>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 日志与错误历史 -->
    <div class="wg" style="margin-bottom: 0">
      <div class="wg-h">
        <u-icon name="hist" />
        <h3>日志与错误历史</h3>
        <span class="x">
          <button class="btn sm" @click="logOpen = true">查看日志</button>
          <button class="btn sm" @click="logOpen = true">错误历史</button>
        </span>
      </div>
      <div class="wg-b small muted">点击右上角按钮弹出日志流弹窗（含「清空错误记录」二次确认）</div>
    </div>

    <!-- 日志弹窗 -->
    <u-modal v-model="logOpen" title="日志与错误历史" icon="hist">
      <div class="logbox num">
        <template v-if="!logsCleared">
          <div
            v-for="(log, i) in d.logs"
            :key="i"
            class="log-line"
            :class="log.level === 'warn' ? 'lv-warn' : log.level === 'bad' ? 'lv-bad' : ''"
          >
            <span class="lt">{{ log.time }}</span
            >{{ log.text }}
          </div>
        </template>
        <div v-else class="log-line muted">错误记录已清空</div>
      </div>
      <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px">
        <u-pop
          v-model="clearPopOpen"
          ok-text="清空"
          cancel-text="取消"
          danger
          @confirm="logsCleared = true"
        >
          <template #trigger>
            <button class="btn sm">清空错误记录</button>
          </template>
          确认清空全部错误记录？该操作不可撤销。
        </u-pop>
        <button class="btn sm pri" @click="logOpen = false">关闭</button>
      </div>
    </u-modal>
  </section>
</template>
