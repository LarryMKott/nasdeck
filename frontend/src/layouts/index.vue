<script setup>
import Sidebar from './components/Sidebar.vue';
import Navbar from './components/Navbar.vue';
import Breadcrumb from './components/Breadcrumb.vue';
import { useAppStore } from '@/stores/modules/app';
import { usePermissionStore } from '@/stores/modules/permission';
import { defaultSettings } from '@/config/settings';

defineOptions({ name: 'MainLayout' });

const appStore = useAppStore();
const permissionStore = usePermissionStore();

const cachedViews = computed(() => permissionStore.cachedViews);
</script>

<template>
  <el-container class="main-layout">
    <el-aside class="main-layout__sidebar" :width="appStore.sidebarCollapsed ? '64px' : '220px'">
      <sidebar />
    </el-aside>

    <el-container class="main-layout__body">
      <el-header class="main-layout__header" height="56px">
        <navbar />
      </el-header>

      <breadcrumb v-if="defaultSettings.showBreadcrumb" class="main-layout__breadcrumb" />

      <el-main class="main-layout__main">
        <router-view v-slot="{ Component, route }">
          <!-- 显式 duration：过渡以定时器收尾，不依赖 transitionend 事件，避免浏览器节流导致动画类不收敛 -->
          <transition name="fade-transform" mode="out-in" appear :duration="200">
            <keep-alive :include="cachedViews">
              <component :is="Component" :key="route.path" />
            </keep-alive>
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<style lang="scss" scoped>
.main-layout {
  height: 100%;

  &__sidebar {
    overflow: hidden;
    background-color: $bg-dark;
    transition: width 0.2s ease;
  }

  &__header {
    padding: 0;
    background-color: #fff;
    border-bottom: 1px solid $border-color;
  }

  &__breadcrumb {
    padding: 12px 16px 0;
  }

  &__main {
    overflow: auto;
  }
}
</style>
