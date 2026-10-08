<script setup>
/** 开机自检动画（花活二期 O，POST 风）：会话首次进入时约 3s BIOS 序列——
 * 主板/CPU/内存/盘数等真实硬件行逐行打出，内存容量滚动计数，末行 OK 后淡入仪表盘。
 * 数据源 detect API 首帧并行拉取：先播过场行（不播数字），数据到位后重建行重打
 * （不放假数据，后端不可达播「不可达」过场）。点击跳过；localStorage「不再播放」；
 * prefers-reduced-motion 直关。纯前端零后端。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { fetchDetect } from '../services/system';

defineOptions({ name: 'UPostSplash' });

const OFF_KEY = 'nd_post_splash';
const PLAYED_KEY = 'nd_post_played';

const visible = ref(false);
const leaving = ref(false);
const lines = ref([]);
const shown = ref(0);
const neverAgain = ref(false);

let typingTimer = 0;
let memTimer = 0;
let finishTimer = 0;

/** 过场行（不含硬件数字；内存行文本随滚动计数原地更新） */
function placeholderLines() {
  return [
    { text: 'NASDECK BIOS v2.3', status: 'OK' },
    { text: '主板 ..........', status: '' },
    { text: 'CPU ..........', status: '' },
    { text: `内存检测 ..........`, status: '' },
    { text: '硬盘 ..........', status: '' },
    { text: '网口 ..........', status: '' },
    { text: '自检完成，进入系统', status: '' },
  ];
}

/** 真实行（detect 数据；缺项状态显"—"，不造假） */
function realLines(d) {
  const kvOf = (rows, key) => rows?.find(([k]) => k === key)?.[1];
  const totalMb = (d.dimms ?? []).reduce((a, m) => a + (parseInt(m.size, 10) || 0), 0);
  const diskN = d.diskSlots?.length || null;
  const nicN = d.network?.length || null;
  const cpu = kvOf(d.cpu?.rows, '型号');
  const cores = kvOf(d.cpu?.rows, '核心 / 线程');
  const mk = (label, val) => ({ text: val ? `${label} ${val}` : label, status: val ? 'OK' : '—' });
  return [
    { text: 'NASDECK BIOS v2.3', status: 'OK' },
    mk('主板', kvOf(d.board, '型号') || kvOf(d.board, '厂商')),
    mk('CPU', [cpu, cores].filter(Boolean).join(' · ')),
    mk('内存检测', totalMb ? `${totalMb} MB` : ''),
    mk('硬盘', diskN ? `${diskN} 盘` : ''),
    mk('网口', nicN ? `${nicN} 口` : ''),
    { text: '自检完成，进入系统', status: 'OK' },
  ];
}

function startTyping() {
  clearInterval(typingTimer);
  shown.value = 0;
  typingTimer = setInterval(() => {
    if (shown.value < lines.value.length) shown.value += 1;
    else clearInterval(typingTimer);
  }, 230);
}

/** 内存滚动计数：700ms 内 0 → totalMb，滚动完重建真实行 */
function startMemRoll(totalMb, onDone) {
  const t0 = performance.now();
  const dur = 700;
  memTimer = setInterval(() => {
    const k = Math.min(1, (performance.now() - t0) / dur);
    const mb = Math.round(totalMb * k);
    const row = lines.value[3];
    if (row) row.text = `内存检测 ${mb} MB ..........`;
    if (k >= 1) {
      clearInterval(memTimer);
      memTimer = 0;
      onDone();
    }
  }, 50);
}

function finish() {
  if (!visible.value || leaving.value) return;
  clearInterval(typingTimer);
  shown.value = lines.value.length;
  leaving.value = true;
  finishTimer = setTimeout(() => {
    visible.value = false;
    sessionStorage.setItem(PLAYED_KEY, '1');
  }, 550);
}

function skip() {
  clearTimers();
  if (neverAgain.value) localStorage.setItem(OFF_KEY, 'off');
  finish();
}

function play() {
  visible.value = true;
  lines.value = placeholderLines();
  startTyping();
  fetchDetect()
    .then(({ data, live }) => {
      if (!visible.value) return; // 已被跳过
      if (!live) {
        lines.value = [
          { text: 'NASDECK BIOS v2.3', status: 'OK' },
          { text: '硬件清单不可达（—）', status: '—' },
          { text: '跳过硬件自检，直接进入', status: 'OK' },
        ];
        startTyping();
        return;
      }
      const totalMb = (data.dimms ?? []).reduce((a, m) => a + (parseInt(m.size, 10) || 0), 0);
      if (totalMb) startMemRoll(totalMb, () => restartIfVisible(data));
      else restartIfVisible(data);
    })
    .catch(() => {});
  // 3s 兜底收尾：数据未到也照常淡入（过场行不等数据）
  finishTimer = setTimeout(finish, 3000);
}

function restartIfVisible(data) {
  if (!visible.value) return;
  lines.value = realLines(data);
  startTyping();
}

function clearTimers() {
  clearInterval(typingTimer);
  clearInterval(memTimer);
  clearTimeout(finishTimer);
  typingTimer = memTimer = finishTimer = 0;
}

onMounted(() => {
  if (localStorage.getItem(OFF_KEY) === 'off') return;
  if (sessionStorage.getItem(PLAYED_KEY)) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  play();
});

onBeforeUnmount(clearTimers);

const shownLines = computed(() => lines.value.slice(0, shown.value));
</script>

<template>
  <div v-if="visible" class="post" :class="{ leaving }" @click="skip">
    <div class="scr">
      <div v-for="(ln, i) in shownLines" :key="i" class="row">
        <span class="tx">{{ ln.text }}</span>
        <span v-if="ln.status" class="st" :class="{ na: ln.status === '—' }">{{
          ln.status === '' ? '' : ln.status
        }}</span>
      </div>
      <div class="cursor" />
    </div>
    <div class="hint">
      <label class="chk" @click.stop>
        <input v-model="neverAgain" type="checkbox" />
        {{ t('不再播放') }}
      </label>
      <span>{{ t('点击任意处跳过') }}</span>
    </div>
  </div>
</template>

<style scoped>
.post {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: ui-monospace, Consolas, Menlo, monospace;
  color: var(--tx0);
  cursor: pointer;
  background: var(--sf);
  opacity: 1;
  transition: opacity 0.5s var(--ease);
}

.post.leaving {
  pointer-events: none;
  opacity: 0;
}

.scr {
  width: min(560px, 86vw);
  min-height: 250px;
  font-size: 13.5px;
  line-height: 2;
}

.row {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  animation: post-in 0.18s steps(3);
}

.tx {
  overflow: hidden;
  white-space: nowrap;
}

.st {
  flex: none;
  color: var(--ok);

  &.na {
    color: var(--tx3);
  }
}

.cursor {
  display: inline-block;
  width: 8px;
  height: 15px;
  background: var(--ok);
  animation: post-blink 0.9s steps(2) infinite;
}

.hint {
  position: fixed;
  bottom: 26px;
  display: flex;
  gap: 18px;
  font-size: 12px;
  color: var(--tx3);
  cursor: default;

  .chk {
    display: inline-flex;
    gap: 5px;
    align-items: center;
    color: var(--tx2);
    cursor: pointer;
  }
}

@keyframes post-in {
  from {
    opacity: 0;
    transform: translateY(3px);
  }

  to {
    opacity: 1;
    transform: none;
  }
}

@keyframes post-blink {
  50% {
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .post {
    transition: none;
  }

  .row {
    animation: none;
  }

  .cursor {
    animation: none;
  }
}
</style>
