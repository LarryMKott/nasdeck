<script setup>
/**
 * UNRAID 稿下拉菜单：#trigger 插槽为触发器，默认插槽为菜单内容。
 * 打开时按触发器矩形 fixed 定位；点击菜单项 / 外部 / Esc 关闭。
 */
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';

defineOptions({ name: 'UDropdown' });

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** 菜单最小宽度 px */
  minWidth: { type: Number, default: 158 },
});

const emit = defineEmits(['update:modelValue']);

const triggerRef = ref(null);
const menuRef = ref(null);

function toggle() {
  emit('update:modelValue', !props.modelValue);
}

function close() {
  emit('update:modelValue', false);
}

function place() {
  const pop = menuRef.value;
  const trig = triggerRef.value;
  if (!pop || !trig) return;
  const r = trig.getBoundingClientRect();
  pop.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - pop.offsetWidth - 8))}px`;
  pop.style.top = `${r.bottom + 6}px`;
}

function onDocClick(e) {
  if (!e.target.closest('.nd-dd-menu') && !e.target.closest('.nd-dd-host')) close();
}

/** 点击菜单项（button）后自动关闭 */
function onMenuClick(e) {
  if (e.target.closest('button')) close();
}

function onKeydown(e) {
  if (e.key === 'Escape') close();
}

watch(
  () => props.modelValue,
  async (open) => {
    if (open) {
      await nextTick();
      place();
      document.addEventListener('click', onDocClick);
      document.addEventListener('keydown', onKeydown);
    } else {
      document.removeEventListener('click', onDocClick);
      document.removeEventListener('keydown', onKeydown);
    }
  }
);

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick);
  document.removeEventListener('keydown', onKeydown);
});
</script>

<template>
  <div ref="triggerRef" class="nd-dd-host" @click.stop="toggle">
    <slot name="trigger" />
  </div>
  <div
    ref="menuRef"
    class="menu nd-dd-menu"
    :class="{ show: modelValue }"
    :style="{ minWidth: `${minWidth}px` }"
    @click="onMenuClick"
  >
    <slot />
  </div>
</template>
