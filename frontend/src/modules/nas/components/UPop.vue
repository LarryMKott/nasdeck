<script setup>
/**
 * UNRAID 稿确认气泡：#trigger 插槽为触发器，默认插槽为确认文案。
 * 右对齐触发器、溢出时上下翻转；取消/确认后关闭并派发事件。
 */
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';

defineOptions({ name: 'UPop' });

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  okText: { type: String, default: '确认' },
  cancelText: { type: String, default: '取消' },
  /** 确认按钮是否为危险样式（红底） */
  danger: { type: Boolean, default: false },
});

const emit = defineEmits(['update:modelValue', 'confirm']);

const triggerRef = ref(null);
const popRef = ref(null);

function toggle() {
  emit('update:modelValue', !props.modelValue);
}

function close() {
  emit('update:modelValue', false);
}

function ok() {
  close();
  emit('confirm');
}

function place() {
  const pop = popRef.value;
  const trig = triggerRef.value;
  if (!pop || !trig) return;
  const r = trig.getBoundingClientRect();
  const pw = pop.offsetWidth;
  const ph = pop.offsetHeight;
  pop.style.left = `${Math.min(Math.max(8, r.right - pw), window.innerWidth - pw - 8)}px`;
  pop.style.top = `${r.bottom + 8 + ph > window.innerHeight ? r.top - ph - 8 : r.bottom + 8}px`;
}

function onDocClick(e) {
  if (!e.target.closest('.nd-pop') && !e.target.closest('.nd-pop-host')) close();
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
  <span ref="triggerRef" class="nd-pop-host" @click.stop="toggle">
    <slot name="trigger" />
  </span>
  <div ref="popRef" class="pop" :class="{ show: modelValue }">
    <slot />
    <div class="acts">
      <button class="btn sm" @click="close">{{ cancelText }}</button>
      <button class="btn sm" :class="danger ? 'stop' : 'pri'" @click="ok">{{ okText }}</button>
    </div>
  </div>
</template>
