<script setup>
/** 命令面板（脑洞 E）：Ctrl+K / / 呼出，模糊搜索页签直达 + 快捷动作。
 * 键盘导航 ↑↓ 选择、Enter 执行、Esc 关闭；输入框聚焦时不接管 `/`。 */
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { navGroups } from '../mock';
import { useIdentityStore } from '../stores/identity';
import UIcon from './UIcon.vue';

defineOptions({ name: 'UCommandPalette' });

const props = defineProps({
  /** 面板开关（v-model，由布局层全局快捷键控制） */
  modelValue: { type: Boolean, default: false },
  /** 快捷动作 { label, icon, run }（布局层注入：切主题/弹幕开关等） */
  actions: { type: Array, default: () => [] },
});
const emit = defineEmits(['update:modelValue']);

const router = useRouter();
const identity = useIdentityStore();
identity.ensure();

const query = ref('');
const activeIdx = ref(0);
const inputEl = ref(null);

/** 候选 = 全部页签 + 头像设置页（管理员）+ 大屏 + 动作 */
const items = computed(() => {
  const pages = navGroups
    .flatMap((g) => g.items)
    .map((i) => ({ kind: '页面', label: i.title, icon: i.icon, path: i.path }));
  pages.push({ kind: '页面', label: '示波器', icon: 'power', path: '/nasdeck/scope' });
  if (identity.canWrite)
    pages.push({
      kind: '页面',
      label: '设置（告警/渠道）',
      icon: 'shield',
      path: '/nasdeck/settings',
    });
  pages.push({ kind: '页面', label: '大屏轮播模式', icon: 'play', path: '/nasdeck/kiosk' });
  const actions = props.actions.map((a) => ({
    kind: '动作',
    label: a.label,
    icon: a.icon,
    run: a.run,
  }));
  return [...pages, ...actions];
});

/** 子序列模糊匹配（大小写不敏感，命中位置越靠前分越高） */
function fuzzy(label, q) {
  if (!q) return 1;
  const l = label.toLowerCase();
  const s = q.toLowerCase();
  let li = 0;
  let score = 0;
  for (const ch of s) {
    const idx = l.indexOf(ch, li);
    if (idx < 0) return 0;
    score += idx === li ? 2 : 1; // 连续命中加分
    li = idx + 1;
  }
  return score;
}

const filtered = computed(() => {
  const q = query.value.trim();
  return items.value
    .map((item) => ({ item, score: fuzzy(item.label, q) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((x) => x.item);
});

watch([query, () => props.modelValue], () => (activeIdx.value = 0));
watch(
  () => props.modelValue,
  async (open) => {
    if (open) {
      query.value = '';
      await nextTick();
      inputEl.value?.focus();
    }
  }
);

function run(item) {
  emit('update:modelValue', false);
  if (item.path) router.push(item.path);
  else item.run?.();
}

function onKeydown(e) {
  if (!props.modelValue) return;
  if (e.key === 'Escape') {
    emit('update:modelValue', false);
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    activeIdx.value = Math.min(activeIdx.value + 1, filtered.value.length - 1);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    activeIdx.value = Math.max(activeIdx.value - 1, 0);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const item = filtered.value[activeIdx.value];
    if (item) run(item);
  }
}

function onGlobalKeydown(e) {
  if (e.key === 'k' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    emit('update:modelValue', !props.modelValue);
  } else if (e.key === '/' && !props.modelValue) {
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement?.isContentEditable) return;
    e.preventDefault();
    emit('update:modelValue', true);
  }
}

onMounted(() => window.addEventListener('keydown', onGlobalKeydown));
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKeydown));
</script>

<template>
  <teleport to="body">
    <div v-if="modelValue" class="cmdk" @keydown="onKeydown">
      <div class="cmdk-mask" @click="emit('update:modelValue', false)" />
      <div class="cmdk-panel">
        <div class="cmdk-search">
          <u-icon name="search" />
          <input
            ref="inputEl"
            v-model="query"
            type="text"
            placeholder="搜索页签或动作…（↑↓ 选择 · Enter 执行 · Esc 关闭）"
          />
        </div>
        <div class="cmdk-list">
          <button
            v-for="(item, i) in filtered"
            :key="item.kind + item.label"
            class="cmdk-i"
            :class="{ on: i === activeIdx }"
            :data-active="i === activeIdx"
            @mouseenter="activeIdx = i"
            @click="run(item)"
          >
            <u-icon :name="item.icon" />
            <span class="lbl">{{ item.label }}</span>
            <span class="kind">{{ item.kind }}</span>
          </button>
          <div v-if="!filtered.length" class="cmdk-empty small muted">无匹配项（—）</div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<style scoped lang="scss">
.cmdk {
  position: fixed;
  inset: 0;
  z-index: 300;
}

.cmdk-mask {
  position: absolute;
  inset: 0;
  background: rgb(0 0 0 / 45%);
}

.cmdk-panel {
  position: absolute;
  top: 14vh;
  left: 50%;
  width: min(560px, 92vw);
  overflow: hidden;
  background: var(--tt);
  border: 1px solid var(--ttbd);
  border-radius: 12px;
  box-shadow: var(--shadow);
  transform: translateX(-50%);
}

.cmdk-search {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 13px 16px;
  border-bottom: 1px solid var(--bd);

  // teleport 到 body 后脱离 .nd，.ico 全局尺寸约束失效——就地兜底
  .ico {
    width: 15px;
    height: 15px;
  }

  input {
    flex: 1;
    font-size: 14.5px;
    background: none;
    border: none;
    outline: none;
  }
}

.cmdk-list {
  max-height: 46vh;
  padding: 6px;
  overflow-y: auto;
}

.cmdk-i {
  display: flex;
  gap: 10px;
  align-items: center;
  width: 100%;
  padding: 9px 12px;
  text-align: left;
  border-radius: 7px;

  .ico {
    width: 14px;
    height: 14px;
  }

  .lbl {
    flex: 1;
    font-size: 13.5px;
  }

  .kind {
    font-size: 11px;
    color: var(--tx3);
  }

  &.on {
    background: var(--accbg);

    .lbl {
      color: var(--acc);
    }
  }
}

.cmdk-empty {
  padding: 18px;
  text-align: center;
}
</style>
