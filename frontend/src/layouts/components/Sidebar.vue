<script setup>
import { Odometer, Setting, User, Avatar } from '@element-plus/icons-vue';
import { useAppStore } from '@/stores/modules/app';
import { usePermissionStore } from '@/stores/modules/permission';
import { defaultSettings } from '@/config/settings';
import logoUrl from '@/assets/images/logo.svg';

defineOptions({ name: 'LayoutSidebar' });

const route = useRoute();
const appStore = useAppStore();
const permissionStore = usePermissionStore();

/** meta.icon 字符串 → 图标组件映射（按需引入，避免全量打包） */
const iconMap = { Odometer, Setting, User, Avatar };

const activeMenu = computed(() => route.path);
const menuRoutes = computed(() => permissionStore.menuRoutes);

/**
 * 解析菜单项完整路径：子路由 path 声明为相对路径时拼接父路径
 * （el-menu router 模式以 index 为跳转目标，必须使用绝对路径）
 * @param {string} parentPath 父路由路径
 * @param {string} [childPath] 子路由路径
 * @returns {string} 绝对路径
 */
function resolveMenuPath(parentPath, childPath) {
  if (!childPath || childPath.startsWith('/')) return childPath || parentPath;
  return `${parentPath}/${childPath}`.replace(/\/+/g, '/');
}

/**
 * 取图标组件
 * @param {string} [name] 图标名称
 * @returns {object | null} 图标组件
 */
function getIcon(name) {
  return name ? (iconMap[name] ?? null) : null;
}
</script>

<template>
  <div class="sidebar">
    <router-link to="/" class="sidebar__logo">
      <img :src="logoUrl" alt="logo" class="sidebar__logo-img" />
      <span v-show="!appStore.sidebarCollapsed" class="sidebar__logo-title">
        {{ defaultSettings.title }}
      </span>
    </router-link>

    <el-scrollbar class="sidebar__scroll">
      <el-menu
        class="sidebar__menu"
        :default-active="activeMenu"
        :collapse="appStore.sidebarCollapsed"
        :collapse-transition="false"
        background-color="#001529"
        text-color="rgba(255, 255, 255, 0.66)"
        active-text-color="#ffffff"
        router
        unique-opened
      >
        <template v-for="item in menuRoutes" :key="item.path">
          <!-- 多子路由：分组菜单 -->
          <el-sub-menu v-if="(item.children ?? []).length > 1" :index="item.path">
            <template #title>
              <el-icon v-if="getIcon(item.meta?.icon)">
                <component :is="getIcon(item.meta.icon)" />
              </el-icon>
              <span>{{ item.meta?.title }}</span>
            </template>
            <el-menu-item
              v-for="child in item.children"
              :key="child.path"
              :index="resolveMenuPath(item.path, child.path)"
            >
              {{ child.meta?.title }}
            </el-menu-item>
          </el-sub-menu>

          <!-- 单子路由：提升为一级菜单 -->
          <el-menu-item v-else :index="resolveMenuPath(item.path, item.children?.[0]?.path)">
            <el-icon v-if="getIcon(item.children?.[0]?.meta?.icon ?? item.meta?.icon)">
              <component :is="getIcon(item.children?.[0]?.meta?.icon ?? item.meta?.icon)" />
            </el-icon>
            <template #title>{{ item.children?.[0]?.meta?.title ?? item.meta?.title }}</template>
          </el-menu-item>
        </template>
      </el-menu>
    </el-scrollbar>
  </div>
</template>

<style lang="scss" scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;

  &__logo {
    display: flex;
    flex-shrink: 0;
    gap: 10px;
    align-items: center;
    justify-content: center;
    height: $navbar-height;
    overflow: hidden;
    background-color: rgb(255 255 255 / 4%);

    &-img {
      width: 28px;
      height: 28px;
      border-radius: 6px;
    }

    &-title {
      @include text-ellipsis;

      font-size: 15px;
      font-weight: 600;
      color: #fff;
      white-space: nowrap;
    }
  }

  &__scroll {
    flex: 1;
  }

  &__menu {
    border-right: none;

    &:not(.el-menu--collapse) {
      width: 100%;
    }
  }
}
</style>
