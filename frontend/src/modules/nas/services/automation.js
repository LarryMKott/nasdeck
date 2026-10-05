'use strict';

/**
 * 自动化视图适配层：firing 告警（总览告警卡/布局铃铛共用）/ 事件流 / 通知渠道。
 */

import * as mock from '../mock';
import { getChannels, getEvents, getFiringEvents } from '../api/endpoints/alert';
import { hhmm, pick } from './shared';

/** firing 告警 → 铃铛/告警卡形状。复用 30s 缓存（fetchDashboard / 布局铃铛 / 本函数）；
 * 后端不可达才演示，空列表 = 无告警是合法真值必须如实展示
 * @returns {Promise<{data: Array<{level: 'bad'|'warn', text: string, time: string, jump: {path: string, action: string}}>, live: boolean}>} */
export async function fetchActiveAlerts() {
  const events = await getFiringEvents().catch(() => null);
  if (events === null) return { data: mock.activeAlerts, live: false }; // 后端不可达才演示
  return {
    data: events.map((e) => ({
      level: e.severity === 'critical' ? 'bad' : 'warn',
      text: e.message || e.rule_name,
      time: hhmm(e.fired_at),
      jump: { path: '/nasdeck/automation', action: '查看告警' },
    })),
    live: true,
  };
}

/** 自动化页取数：事件流（limit=10）+ firing 告警 + 通知渠道
 * @returns {Promise<{data: object, live: boolean}>} */
export async function fetchAutomation() {
  const [eventsS, activeS, chansS] = await Promise.allSettled([
    getEvents(10),
    fetchActiveAlerts(),
    getChannels(),
  ]);
  const events = pick(eventsS) ?? [];
  const active = pick(activeS) ?? { data: [], live: false };
  const channels = pick(chansS);
  return {
    data: {
      activeAlerts: active.data,
      // 日志与错误历史 = 告警事件流（后端无独立日志接口，不再展开 mock 假日志）
      recentEvents: events.map((e) => ({
        ...e,
        time: hhmm(e.fired_at),
      })),
      // 通知渠道真实清单（名称/type），测试通知按钮据此接线
      channels: (channels ?? []).map((c) => ({ id: c.id, name: c.name, type: c.type })),
    },
    live: active.live,
  };
}
