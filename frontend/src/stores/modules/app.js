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
    /** UNRAID 界面主题：dark（默认）| light | system | cyber（赛博朋克）| terminal（终端绿 CRT） */
    theme: 'dark',
    /** 系统是否偏好暗色（prefers-color-scheme，theme 为 system 时据此解析） */
    systemPrefersDark: false,
  }),

  getters: {
    /** 实际生效的主题：system 按系统偏好解析，其余（含花活皮肤）原样返回 */
    resolvedTheme() {
      if (this.theme !== 'system') return this.theme;
      return this.systemPrefersDark ? 'dark' : 'light';
    },
  },

  actions: {
    /** 切换侧边栏折叠状态 */
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed;
    },

    /** 切换 UNRAID 界面主题：dark → light → system → cyber → terminal 循环 */
    toggleTheme() {
      const order = ['dark', 'light', 'system', 'cyber', 'terminal'];
      this.theme = order[(order.indexOf(this.theme) + 1) % order.length];
    },

    /** 监听系统配色变化，供「跟随系统」模式实时联动；应用入口调用一次 */
    initThemeWatcher() {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      this.systemPrefersDark = mq.matches;
      // 老 webview（iOS Safari <14 等）MediaQueryList 未继承 EventTarget，只有废弃的 addListener
      const on = (e) => {
        this.systemPrefersDark = e.matches;
      };
      if (typeof mq.addEventListener === 'function') mq.addEventListener('change', on);
      else if (typeof mq.addListener === 'function') mq.addListener(on);
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
