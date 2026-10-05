'use strict';

/**
 * 自动化视图适配层：firing 告警（总览告警卡/布局铃铛共用）/ 事件流 / 通知渠道。
 */

import * as mock from '../mock';
import { getChannels, getEvents, getFiringEvents, getRules } from '../api/endpoints/alert';
import { getReportSchedule, getSelftestSchedule } from '../api/endpoints/system';
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

/** 自动化页取数：事件流（limit=10）+ firing 告警 + 通知渠道 + 规则 + 巡检计划
 * @returns {Promise<{data: object, live: boolean}>} */
export async function fetchAutomation() {
  const [eventsS, activeS, chansS, rulesS, schedS, reportS] = await Promise.allSettled([
    getEvents(10),
    fetchActiveAlerts(),
    getChannels(),
    getRules(),
    getSelftestSchedule(),
    getReportSchedule(),
  ]);
  const events = pick(eventsS) ?? [];
  const active = pick(activeS) ?? { data: [], live: false };
  const channels = pick(chansS);
  const rules = pick(rulesS);
  const schedule = pick(schedS);
  const demo = !active.live; // 整页演示回退时渠道/规则也取演示值；live 时单路失败如实为空
  return {
    data: {
      activeAlerts: active.data,
      // 日志与错误历史 = 告警事件流（后端无独立日志接口，不再展开 mock 假日志）
      recentEvents: events.map((e) => ({
        ...e,
        time: hhmm(e.fired_at),
      })),
      // 通知渠道真实清单（含启用态与脱敏配置，渠道管理/规则多选数据源）
      channels: demo && !channels ? mock.alertChannels : (channels ?? []),
      rules: demo && !rules ? mock.alertRules : (rules ?? []),
      // 巡检计划（live 时真实值；演示回退用缺省关闭态，不虚构"上周已跑"）
      selftestSchedule: schedule ?? mock.selftestSchedule,
      // 周报推送计划（单路失败为 null，视图按关闭态渲染）
      reportSchedule: pick(reportS) ?? null,
    },
    live: active.live,
  };
}

/** 事件时间线取数（M3.2 统一时间线）：source 过滤 + mock 演示回退
 * @param {'all'|'alert'|'system'} [source]
 * @param {number} [limit]
 * @returns {Promise<{data: {list: Array}, live: boolean}>} */
export async function fetchTimeline(source = 'all', limit = 200) {
  try {
    const events = await getEvents(limit, source);
    return { data: { list: events.map((e) => ({ ...e, time: hhmm(e.fired_at) })) }, live: true };
  } catch {
    return { data: { list: mock.timeline }, live: false };
  }
}
