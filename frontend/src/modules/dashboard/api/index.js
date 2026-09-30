'use strict';

/** 工作台模块 API */
import { get } from '@/utils/request';

/**
 * 获取工作台概览数据（统计卡片 + 最近动态）
 * @returns {Promise<{code: number, data: {summary: Array, logs: Array}, message: string}>}
 */
export function getDashboardOverview() {
  return get('/dashboard/overview');
}
