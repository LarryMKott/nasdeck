<script setup>
/** 事件时间线（M3.2 统一时间线）：告警与系统级事件（巡检/容器退出/端口异动/日志哨兵）一屏回溯 */
import { computed, ref } from 'vue';
import { useViewData } from '../composables/useViewData';
import { fetchTimeline } from '../services/automation';
import UPageHeader from '../components/UPageHeader.vue';

defineOptions({ name: 'NasTimeline' });

// 初始空骨架；mock 只在后端不可达时由适配层整页演示回退
const {
  data: d,
  live,
  lastUpdated,
} = useViewData(() => fetchTimeline(source.value, 200), { list: [] });

/** 来源过滤：all 全部 / alert 规则告警 / system 系统级（rule_id 为空） */
const source = ref('all');

const SEVERITY_META = {
  critical: { color: 'var(--bad)', text: '严重' },
  warning: { color: 'var(--warn)', text: '警告' },
  info: { color: 'var(--info)', text: '信息' },
};

/** 行状态：firing 红 / resolved 按严重级着色 */
function rowColor(e) {
  if (e.status === 'firing') return 'var(--bad)';
  return SEVERITY_META[e.severity]?.color || 'var(--tx3)';
}

function severityText(e) {
  const raw = SEVERITY_META[e.severity]?.text || e.severity;
  return t(raw);
}

/** 系统级事件显示类型徽标（rule_name 已带语义），规则事件显示规则名 */
function sourceText(e) {
  return e.rule_id != null ? t('告警') : t('系统');
}

const headerTag = computed(() => {
  if (!live.value) return { type: 'acc', text: t('演示数据') };
  const firing = d.value.list.filter((e) => e.status === 'firing').length;
  return {
    type: firing ? 'warn' : 'ok',
    text: firing ? t('{n} 条活跃', { n: firing }) : t('全部平静'),
  };
});
</script>

<template>
  <section>
    <u-page-header
      :title="t('事件时间线')"
      :sub="t('告警 · 系统事件 一屏回溯')"
      :tag="headerTag"
      :updated="lastUpdated"
    />

    <div class="chips" style="margin-bottom: 14px">
      <button :class="{ on: source === 'all' }" @click="source = 'all'">{{ t('全部') }}</button>
      <button :class="{ on: source === 'alert' }" @click="source = 'alert'">{{ t('告警') }}</button>
      <button :class="{ on: source === 'system' }" @click="source = 'system'">
        {{ t('系统') }}
      </button>
    </div>

    <div class="wg">
      <div class="wg-b">
        <template v-if="d.list.length">
          <div class="nd-tl">
            <div v-for="e in d.list" :key="e.id" class="nd-tl-i">
              <span class="nd-tl-dot" :style="{ background: rowColor(e) }" />
              <div class="nd-tl-c">
                <div class="row" style="display: flex; gap: 8px; align-items: baseline">
                  <span class="num small muted">{{ e.time }}</span>
                  <b class="small">{{ e.rule_name }}</b>
                  <span
                    class="tag"
                    :class="sourceText(e) === t('告警') ? 'acc' : ''"
                    style="height: 19px"
                  >
                    {{ sourceText(e) }} · {{ severityText(e) }}
                  </span>
                  <span v-if="e.status === 'firing'" class="tag warn" style="height: 19px">{{
                    t('进行中')
                  }}</span>
                </div>
                <div class="small" style="margin-top: 3px">{{ e.message || '—' }}</div>
              </div>
            </div>
          </div>
        </template>
        <div v-else class="small muted" style="padding: 20px 0; text-align: center">
          {{
            t('暂无事件记录（—）：告警触发、巡检、容器退出、端口异动、日志哨兵命中都会出现在这里')
          }}
        </div>
      </div>
    </div>
  </section>
</template>
