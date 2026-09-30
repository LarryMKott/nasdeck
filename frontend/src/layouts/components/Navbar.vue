<script setup>
import { ArrowDown, Expand, Fold, SwitchButton, UserFilled } from '@element-plus/icons-vue';
import Breadcrumb from './Breadcrumb.vue';
import { useAppStore } from '@/stores/modules/app';
import { useUserStore } from '@/stores/modules/user';

defineOptions({ name: 'LayoutNavbar' });

const router = useRouter();
const appStore = useAppStore();
const userStore = useUserStore();

/**
 * 下拉菜单命令处理
 * @param {string} command 命令标识
 */
async function handleCommand(command) {
  if (command !== 'logout') return;
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
    });
  } catch {
    return;
  }
  await userStore.logout();
  ElMessage.success('已安全退出');
  router.replace('/login');
}
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
      <el-dropdown trigger="click" @command="handleCommand">
        <span class="navbar__user">
          <el-avatar :size="30" :icon="UserFilled" />
          <span class="navbar__username">{{ userStore.nickname }}</span>
          <el-icon :size="12"><arrow-down /></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="logout" :icon="SwitchButton">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
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
    cursor: pointer;
  }

  &__username {
    @include text-ellipsis;

    max-width: 140px;
    color: $color-text-primary;
  }
}
</style>
