<script setup>
/** 系统自检（原型 E2）：五组检查清单 + 修复建议；跳转入口给铃铛/排障。 */
import { computed, onActivated, onMounted, ref } from 'vue';
import { apiData } from '../api/client';
import UPageHeader from '../components/UPageHeader.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasSelfCheck' });

const result = ref(null);
const loadError = ref('');
const refreshing = ref(false);
const lastUpdated = ref('—');

let seq = 0;
async function refresh() {
  const my = ++seq;
  refreshing.value = true;
  loadError.value = '';
  try {
    result.value = await apiData('/api/v1/system/diagnostics');
  } catch (e) {
    if (my === seq) loadError.value = e?.message || '自检接口不可达';
  } finally {
    if (my === seq) {
      refreshing.value = false;
      const now = new Date();
      const pad = (x) => String(x).padStart(2, '0');
      lastUpdated.value = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    }
  }
}

onMounted(refresh);
onActivated(refresh);

const summary = computed(() => {
  const counts = { ok: 0, warn: 0, fail: 0, skip: 0 };
  for (const g of result.value?.groups || []) {
    for (const it of g.items) counts[it.status] = (counts[it.status] || 0) + 1;
  }
  return counts;
});

const headerTag = computed(() => {
  if (loadError.value) return { type: 'warn', text: '接口不可达' };
  if (!result.value) return { type: 'acc', text: '检查中…' };
  if (summary.value.fail) return { type: 'warn', text: `${summary.value.fail} 项异常` };
  if (summary.value.warn) return { type: 'warn', text: `${summary.value.warn} 项告警` };
  return { type: 'ok', text: '全部正常' };
});

const STATUS_LABEL = { ok: '正常', warn: '告警', fail: '异常', skip: '不适用' };
</script>

<template>
  <section>
    <u-page-header
      :refreshing="refreshing"
      title="系统自检"
      sub="数据管线 · 风扇 · 鉴权链 · 采集工具 · 通知"
      :tag="headerTag"
      :updated="lastUpdated"
      @refresh="refresh"
    />

    <div v-if="loadError" class="wg">
      <div class="wg-b small" style="color: var(--bad, #e5484d)">
        自检接口不可达：{{ loadError }}（后端未启动或网关未转发时无法自检）
      </div>
    </div>

    <div v-else-if="result" class="wg" style="margin-bottom: 12px">
      <div class="wg-b" style="display: flex; flex-wrap: wrap; gap: 18px; align-items: center">
        <span><span class="dot ok" />正常 {{ summary.ok }}</span>
        <span style="color: var(--warn, #eca43c)"
          ><span class="dot warn" />告警 {{ summary.warn }}</span
        >
        <span style="color: var(--bad, #e5484d)"
          ><span class="dot bad" />异常 {{ summary.fail }}</span
        >
        <span class="muted"
          ><span class="dot" style="background: var(--tx3)" />不适用 {{ summary.skip }}</span
        >
        <button class="btn sm" style="margin-left: auto" :disabled="refreshing" @click="refresh">
          {{ refreshing ? '检查中…' : '重新检查' }}
        </button>
      </div>
    </div>

    <div v-for="g in result?.groups || []" :key="g.name" class="wg" style="margin-bottom: 12px">
      <div class="wg-h">
        <u-icon name="shield" />
        <h3>{{ g.name }}</h3>
      </div>
      <div class="wg-b" style="padding-top: 0">
        <div
          v-for="it in g.items"
          :key="it.key"
          class="chk"
          :class="it.status"
          style="
            display: flex;
            gap: 10px;
            align-items: flex-start;
            padding: 9px 12px;
            margin-bottom: 7px;
            border: 1px solid var(--bd, #323338);
            border-radius: 5px;
          "
        >
          <span
            class="dot"
            :style="{
              background:
                it.status === 'ok'
                  ? 'var(--ok, #3fb68b)'
                  : it.status === 'warn'
                    ? 'var(--warn, #eca43c)'
                    : it.status === 'fail'
                      ? 'var(--bad, #e5484d)'
                      : 'var(--tx3, #5b5d65)',
              marginTop: '6px',
            }"
          />
          <div style="flex: 1">
            <div style="font-weight: 600">
              {{ it.key }}
              <span class="small muted">· {{ STATUS_LABEL[it.status] }}</span>
            </div>
            <div class="small muted" style="margin-top: 1px">{{ it.detail }}</div>
            <div v-if="it.hint" class="small" style="margin-top: 5px; color: var(--info, #5b9cf6)">
              建议：{{ it.hint }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
