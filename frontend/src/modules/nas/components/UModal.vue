<script setup>
/** UNRAID 稿弹窗：居中卡片 + 遮罩，Esc / 遮罩 / 关闭按钮均可关闭 */
import { onBeforeUnmount, watch } from 'vue';

defineOptions({ name: 'UModal' });

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, required: true },
  icon: { type: String, default: 'info' },
});

const emit = defineEmits(['update:modelValue']);

function close() {
  emit('update:modelValue', false);
}

function onKeydown(e) {
  if (e.key === 'Escape') close();
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) document.addEventListener('keydown', onKeydown);
    else document.removeEventListener('keydown', onKeydown);
  }
);

onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown));
</script>

<template>
  <div class="mask" :class="{ show: modelValue }" @click="close" />
  <div class="modal" :class="{ show: modelValue }">
    <div class="wg-h">
      <svg class="ico"><use :href="`#nd-i-${icon}`" /></svg>
      <h3>{{ title }}</h3>
      <span class="x">
        <button class="iconbtn" title="关闭" @click="close">
          <svg class="ico"><use href="#nd-i-x" /></svg>
        </button>
      </span>
    </div>
    <div class="wg-b">
      <slot />
    </div>
  </div>
</template>
