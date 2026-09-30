'use strict';

/** 工作台模块状态 */
import { defineStore } from 'pinia';
import { getDashboardOverview } from '../api';

export const useDashboardStore = defineStore('dashboard', {
  state: () => ({
    /** 概览加载中 */
    loading: false,
    /** 统计卡片数据 */
    summary: [],
    /** 最近动态 */
    logs: [],
  }),

  actions: {
    /** 拉取工作台概览数据 */
    async fetchOverview() {
      this.loading = true;
      try {
        const res = await getDashboardOverview();
        this.summary = res.data?.summary ?? [];
        this.logs = res.data?.logs ?? [];
      } finally {
        this.loading = false;
      }
    },
  },
});
