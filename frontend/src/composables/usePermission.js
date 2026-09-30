'use strict';

/** 权限判断组合式函数：供指令、组件、逻辑层统一使用 */
import { useUserStore } from '@/stores/modules/user';

export function usePermission() {
  const userStore = useUserStore();

  /**
   * 判断当前用户是否拥有指定权限（任一命中即通过）
   * @param {string[]} [permissions] 权限标识数组
   * @returns {boolean}
   */
  function hasPermission(permissions) {
    if (!Array.isArray(permissions) || !permissions.length) return true;
    return permissions.some((permission) => userStore.permissions.includes(permission));
  }

  return { hasPermission };
}
