'use strict';

/** 应用全局状态：侧边栏折叠、设备类型、组件尺寸、UNRAID 界面主题 */
import { defineStore } from 'pinia';
import { STORAGE_PREFIX } from '@/constants';

export const useAppStore = defineStore('app', {
  state: () => ({
    /** 侧边栏是否折叠 */
    sidebarCollapsed: false,
    /** 设备类型：desktop | mobile */
    device: 'desktop',
    /** Element Plus 组件尺寸：large | default | small */
    size: 'default',
    /** UNRAID 界面主题：dark（默认）| light */
    theme: 'dark',
  }),

  actions: {
    /** 切换侧边栏折叠状态 */
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed;
    },

    /** 切换 UNRAID 界面黑/白主题 */
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
    },

    /**
     * 设置设备类型
     * @param {'desktop' | 'mobile'} device 设备类型
     */
    setDevice(device) {
      this.device = device;
    },

    /**
     * 设置全局组件尺寸
     * @param {'large' | 'default' | 'small'} size 尺寸
     */
    setSize(size) {
      this.size = size;
    },
  },

  // 状态持久化：仅持久化需要跨会话保留的字段
  persist: {
    key: `${STORAGE_PREFIX}app`,
    storage: localStorage,
    paths: ['sidebarCollapsed', 'size', 'theme'],
  },
});
