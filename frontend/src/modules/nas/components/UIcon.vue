<script setup>
/** UNRAID 稿线性图标：引用 IconSprite 中的 symbol（id = nd-i-<name>） */
defineOptions({ name: 'UIcon' });

defineProps({
  /** 图标名（如 dash / array / drive，完整清单见 IconSprite.vue） */
  name: { type: String, required: true },
});
</script>

<template>
  <svg class="ico" aria-hidden="true"><use :href="`#nd-i-${name}`" /></svg>
</template>
