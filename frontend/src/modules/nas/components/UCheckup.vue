<script setup>
/** 一键体检（花活二期 N）：全屏序列动画逐项检查打勾 → 总分环 SVG 描边揭晓 →
 * 分享 PNG（复用脑洞 B canvas 模块）。纯聚合只读；动画可跳过（点遮罩或按 Esc）；
 * prefers-reduced-motion 直出结果页。后端不可达显式报错，不造假分。 */
import { computed, ref } from 'vue';
import { getCheckup } from '../api/endpoints/monitor';
import { downloadCheckupCard } from '../utils/statusCard';

defineOptions({ name: 'UCheckup' });

const ITEM_LABELS = {
  oracle: '硬盘预言',
  capacity: '容量预测',
  raid: '阵列状态',
  temp: '温度余量',
  alerts: '30 天告警',
  ports: '端口暴露面',
};

const open = ref(false);
const phase = ref('idle'); // idle/loading/reveal/error
const result = ref(null);
const revealed = ref(0); // 已点亮的体检项数
const ringOn = ref(false); // 总分环描边动画开关（数据到齐后置 true）
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

let timers = [];

function clearTimers() {
  timers.forEach(clearTimeout);
  timers = [];
}

async function run() {
  clearTimers();
  open.value = true;
  phase.value = 'loading';
  result.value = null;
  revealed.value = 0;
  ringOn.value = false;
  try {
    const r = await getCheckup();
    result.value = r;
    if (reduced) {
      phase.value = 'reveal';
      revealed.value = r.items.length;
      ringOn.value = true;
      return;
    }
    phase.value = 'reveal';
    r.items.forEach((_, i) => {
      timers.push(setTimeout(() => (revealed.value = i + 1), 320 * (i + 1)));
    });
    // 全项点亮后总分环描边
    timers.push(setTimeout(() => (ringOn.value = true), 320 * (r.items.length + 1)));
  } catch {
    phase.value = 'error';
  }
}

/** 跳过动画：全部立即点亮 */
function skipAnim() {
  if (phase.value !== 'reveal' || !result.value) return;
  clearTimers();
  revealed.value = result.value.items.length;
  ringOn.value = true;
}

function close() {
  clearTimers();
  open.value = false;
  phase.value = 'idle';
}

function onKey(e) {
  if (e.key === 'Escape') close();
}

function share() {
  if (result.value) downloadCheckupCard(result.value);
}

defineExpose({ run });

const scoreColor = computed(() => {
  const g = result.value?.grade;
  return g === 'ok' ? 'var(--ok)' : g === 'warn' ? 'var(--warn)' : 'var(--bad)';
});

/** 总分环几何：r=62，周长 2πr；dashoffset 由 ringOn 驱动 CSS 过渡 */
const RING_R = 62;
const RING_C = 2 * Math.PI * RING_R;
const ringOffset = computed(() => {
  const s = result.value?.score;
  if (s == null) return RING_C;
  return RING_C * (1 - Math.min(100, Math.max(0, s)) / 100);
});

const shownItems = computed(() => result.value?.items?.slice(0, revealed.value) ?? []);
</script>

<template>
  <!-- 不用 teleport：主题令牌定义在 .nd 根，teleport 到 body 会失去变量；
       固定定位不受布局滚动影响，祖先无持久 transform（nd-vin 是无 fill 动画） -->
  <div
    v-if="open"
    class="ckup"
    @click="phase === 'reveal' && !ringOn ? skipAnim() : null"
    @keydown.esc="onKey"
  >
    <div class="panel" role="dialog" :aria-label="t('一键体检')">
      <div class="head">
        <h3>{{ t('一键体检') }}</h3>
        <button class="x" @click="close">✕</button>
      </div>

      <div v-if="phase === 'loading'" class="body loading">
        <span class="spin" />{{ t('正在体检…') }}
      </div>

      <div v-else-if="phase === 'error'" class="body error small">
        {{ t('体检不可用（—）：后端不可达，不显示假分') }}
      </div>

      <div v-else class="body" :class="{ skipable: !ringOn }">
        <div class="rows">
          <div v-for="it in shownItems" :key="it.key" class="row">
            <span class="ic" :class="it.status">
              {{ it.status === 'ok' ? '✓' : it.status === 'warn' ? '!' : '✕' }}
            </span>
            <span class="lb">{{ t(ITEM_LABELS[it.key] || it.key) }}</span>
            <span class="dt small muted">{{ it.detail }}</span>
            <b class="num" :class="it.status">{{
              it.score != null ? Math.round(it.score) : '—'
            }}</b>
          </div>
        </div>
        <div class="ring-col">
          <svg class="ring" viewBox="0 0 160 160">
            <circle cx="80" cy="80" :r="RING_R" fill="none" stroke="var(--sf3)" stroke-width="10" />
            <circle
              cx="80"
              cy="80"
              :r="RING_R"
              fill="none"
              :stroke="scoreColor"
              stroke-width="10"
              stroke-linecap="round"
              stroke-dasharray="390"
              :stroke-dashoffset="ringOn ? ringOffset : 390"
              transform="rotate(-90 80 80)"
              class="ring-fg"
            />
            <text x="80" y="74" text-anchor="middle" class="num rv" :style="{ fill: scoreColor }">
              {{ ringOn && result?.score != null ? result.score : '—' }}
            </text>
            <text x="80" y="98" text-anchor="middle" class="rl">/ 100</text>
          </svg>
          <div class="acts">
            <button class="btn sm go" :disabled="!ringOn" @click="share">
              {{ t('生成分享 PNG') }}
            </button>
            <button class="btn sm" @click="close">{{ t('关闭') }}</button>
          </div>
        </div>
      </div>
      <div v-if="phase === 'reveal' && !ringOn" class="hint small muted">
        {{ t('点击任意处跳过动画') }}
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.ckup {
  position: fixed;
  inset: 0;
  z-index: 2600;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgb(0 0 0 / 62%);
  backdrop-filter: blur(3px);
}

.panel {
  width: min(660px, 94vw);
  max-height: 88vh;
  padding: 18px 20px 16px;
  overflow: auto;
  background: var(--sf2);
  border: 1px solid var(--bd2);
  border-radius: 12px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;

  h3 {
    margin: 0;
    font-size: 16px;
  }

  .x {
    padding: 2px 8px;
    color: var(--tx2);
    cursor: pointer;
    background: none;
    border: none;

    &:hover {
      color: var(--tx0);
    }
  }
}

.body {
  display: flex;
  gap: 24px;
  align-items: center;

  &.loading,
  &.error {
    gap: 10px;
    justify-content: center;
    padding: 46px 0;
    color: var(--tx2);
  }
}

.rows {
  flex: 1;
  min-width: 300px;
}

.row {
  display: grid;
  grid-template-columns: 26px 92px 1fr 44px;
  gap: 10px;
  align-items: center;
  padding: 7px 0;
  border-bottom: 1px dashed var(--bd);
  animation: ckup-in 0.22s var(--ease);

  &:last-child {
    border-bottom: none;
  }

  .ic {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    font-size: 13px;
    font-weight: 700;
    border-radius: 50%;

    &.ok {
      color: var(--ok);
      background: var(--okbg);
    }

    &.warn {
      color: var(--warn);
      background: var(--warnbg);
    }

    &.bad {
      color: var(--bad);
      background: var(--badbg);
    }
  }

  b {
    text-align: right;

    &.ok {
      color: var(--ok);
    }

    &.warn {
      color: var(--warn);
    }

    &.bad {
      color: var(--bad);
    }
  }
}

.ring-col {
  flex: none;
  text-align: center;
}

.ring {
  width: 172px;

  .ring-fg {
    transition: stroke-dashoffset 0.9s var(--ease);
  }

  .rv {
    font-size: 34px;
    font-weight: 800;
  }

  .rl {
    font-size: 12px;
    fill: var(--tx3);
  }
}

.acts {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-top: 10px;
}

.hint {
  margin-top: 10px;
  text-align: center;
}

.spin {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--bd);
  border-top-color: var(--acc);
  border-radius: 50%;
  animation: ckup-rotate 0.8s linear infinite;
}

@keyframes ckup-in {
  from {
    opacity: 0;
    transform: translateX(-8px);
  }

  to {
    opacity: 1;
    transform: none;
  }
}

@keyframes ckup-rotate {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .row {
    animation: none;
  }

  .ring .ring-fg {
    transition: none;
  }

  .spin {
    animation: none;
  }
}
</style>
