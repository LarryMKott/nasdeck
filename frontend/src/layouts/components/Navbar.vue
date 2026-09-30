<script setup>
import { Expand, Fold, UserFilled } from '@element-plus/icons-vue';
import Breadcrumb from './Breadcrumb.vue';
import { useAppStore } from '@/stores/modules/app';
import { useUserStore } from '@/stores/modules/user';

defineOptions({ name: 'LayoutNavbar' });

const appStore = useAppStore();
const userStore = useUserStore();
</script>

<template>
  <div class="navbar">
    <div class="navbar__left">
      <el-icon class="navbar__trigger" :size="18" @click="appStore.toggleSidebar()">
        <component :is="appStore.sidebarCollapsed ? Expand : Fold" />
      </el-icon>
      <breadcrumb />
    </div>

    <div class="navbar__right">
      <span class="navbar__user">
        <el-avatar :size="30" :icon="UserFilled" />
        <span class="navbar__username">{{ userStore.nickname }}</span>
      </span>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
  padding: 0 16px;

  &__left {
    display: flex;
    gap: 16px;
    align-items: center;
  }

  &__trigger {
    color: $color-text-primary;
    cursor: pointer;
  }

  &__user {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  &__username {
    @include text-ellipsis;

    max-width: 140px;
    color: $color-text-primary;
  }
}
</style>
