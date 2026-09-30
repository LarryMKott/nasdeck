'use strict';

/** 自定义指令：权限控制（元素级） */
import { usePermission } from '@/composables/usePermission';

/**
 * 检查权限并移除无权限元素
 * @param {HTMLElement} el 挂载元素
 * @param {{ value: string[] }} binding 指令绑定值：权限标识数组
 */
function check(el, binding) {
  const value = binding.value;
  if (!Array.isArray(value) || !value.length) return;
  const { hasPermission } = usePermission();
  if (!hasPermission(value)) el.parentNode?.removeChild(el);
}

export const permission = {
  mounted: check,
  updated: check,
};
