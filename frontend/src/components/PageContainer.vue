<script setup>
/**
 * 页面容器：统一页面外层留白、卡片头部与操作区插槽。
 * 全局组件（src/components）由 unplugin-vue-components 自动导入，无需 import。
 */
defineOptions({ name: 'PageContainer' });

defineProps({
  /** 卡片标题 */
  title: { type: String, default: '' },
});
</script>

<template>
  <div class="page-container">
    <el-card shadow="never" class="page-container__card">
      <template v-if="title || $slots.header" #header>
        <div class="page-container__header">
          <span class="page-container__title">{{ title }}</span>
          <div class="page-container__extra">
            <slot name="header" />
          </div>
        </div>
      </template>
      <slot />
    </el-card>
  </div>
</template>

<style lang="scss" scoped>
.page-container {
  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  &__title {
    font-size: 16px;
    font-weight: 600;
  }

  &__extra {
    display: flex;
    gap: 8px;
    align-items: center;
  }
}
</style>
