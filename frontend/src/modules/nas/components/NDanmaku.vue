<script setup>
/** 事件弹幕（花活 H）：WS alert 帧 → 顶栏下方飘过的事件小字，纯氛围不挡操作。
 * 开关存 localStorage（nd_danmaku，默认关）；布局铃铛菜单派发 CustomEvent 切换。
 * 同事件 id 去重（WS 重连后 latest_alert_events 缓存重放不重复飘）；同屏限 3 条。 */
import { onBeforeUnmount, ref, watchEffect } from 'vue';
import { storeToRefs } from 'pinia';
import { useRealtimeStore } from '../stores/realtime';

defineOptions({ name: 'NDanmaku' });

const KEY = 'nd_danmaku';
const enabled = ref(localStorage.getItem(KEY) === '1');

function onToggle(e) {
  enabled.value = !!e.detail;
  if (!enabled.value) items.value = [];
}
window.addEventListener('nd-danmaku-toggle', onToggle);
onBeforeUnmount(() => window.removeEventListener('nd-danmaku-toggle', onToggle));

const items = ref([]);
const seen = new Set();
const COLORS = { critical: 'var(--bad)', warning: 'var(--warn)', info: 'var(--ok)' };

const realtime = useRealtimeStore();
const { lastAlert } = storeToRefs(realtime);
let seq = 0;

const stop = watchEffect(() => {
  const e = lastAlert.value;
  if (!e || !enabled.value || e.id == null || seen.has(e.id)) return;
  seen.add(e.id);
  if (seen.size > 200) seen.clear();
  if (items.value.length >= 3) items.value.shift();
  items.value.push({
    key: `${e.id}-${seq++}`,
    text: `${e.rule_name} · ${e.message || ''}`.slice(0, 48),
    color: COLORS[e.severity] || 'var(--tx2)',
  });
});
onBeforeUnmount(stop);

function onEnd(item) {
  items.value = items.value.filter((x) => x.key !== item.key);
}
</script>

<template>
  <div v-if="enabled" class="nd-danmaku" aria-hidden="true">
    <div
      v-for="item in items"
      :key="item.key"
      class="nd-danmaku-i"
      :style="{ color: item.color }"
      @animationend="onEnd(item)"
    >
      {{ item.text }}
    </div>
  </div>
</template>

<style scoped>
.nd-danmaku {
  position: fixed;
  top: 58px;
  right: 0;
  left: 0;
  z-index: 45;
  height: 0;
  pointer-events: none;
}

.nd-danmaku-i {
  position: absolute;
  right: -420px;
  overflow: hidden;
  font-size: 12.5px;
  font-weight: 600;
  text-shadow: 0 1px 4px rgb(0 0 0 / 60%);
  white-space: nowrap;
  animation: nd-danmaku-fly 9s linear forwards;
}

@keyframes nd-danmaku-fly {
  0% {
    opacity: 0.95;
    transform: translateX(0);
  }

  85% {
    opacity: 0.85;
  }

  100% {
    opacity: 0;
    transform: translateX(calc(-100vw - 420px));
  }
}
</style>
