<script setup>
/** 全局 toast 渲染栈（挂在 UnraidLayout 根部，一次挂载全局可用）。 */
import { useToasts } from '../composables/useToast';

defineOptions({ name: 'UToast' });
const toasts = useToasts();
</script>

<template>
  <transition-group name="toast" tag="div" class="toast-stack">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="t.kind">{{ t.message }}</div>
  </transition-group>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  top: 14px;
  right: 14px;
  z-index: 200;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 380px;
  pointer-events: none;
}

.toast {
  padding: 9px 14px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--tx0, #f0f0f2);
  background: var(--sf2, #242529);
  border: 1px solid var(--bd, #323338);
  border-left: 3px solid var(--info, #5b9cf6);
  border-radius: 5px;
  box-shadow: 0 10px 32px rgb(0 0 0 / 50%);
}

.toast.ok {
  border-left-color: var(--ok, #3fb68b);
}

.toast.bad {
  border-left-color: var(--bad, #e5484d);
}

.toast.warn {
  border-left-color: var(--warn, #eca43c);
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.25s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(14px);
}
</style>
