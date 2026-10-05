'use strict';

/**
 * 监控视图适配层：温度墙 / 系统资源图表（SystemView）/ 历史序列（SysHistView）。
 */

import * as mock from '../mock';
import {
  getHistory,
  getHistoryStats,
  getRealtime,
  getTemperatures,
} from '../api/endpoints/monitor';
import { pick } from './shared';

/** 图表维度 → HistoryPoint 字段 */
const DIM_FIELDS = {
  cpu: 'cpu_avg',
  mem: 'mem_avg_mb',
  temp: 'temp_max_c',
  net: 'net_avg_kbps',
  disk: 'disk_read_kbps',
  gpu: 'gpu_avg',
};

/** 温度页取数：按 zone 聚合磁贴 + 全量温度墙
 * @returns {Promise<{data: {tiles: Array, wall: Array}, live: boolean}>} */
export async function fetchTemps() {
  const items = await getTemperatures().catch(() => null);
  if (!items?.length) return { data: mock.temps, live: false };
  const byZone = (zone) => items.filter((t) => t.zone === zone);
  const tile = (zone, icon, label) => {
    const list = byZone(zone);
    if (!list.length) return null;
    return { key: zone, icon, label, tempC: Math.round(Math.max(...list.map((t) => t.celsius))) };
  };
  const tiles = [
    tile('cpu', 'cpu', 'CPU'),
    tile('board', 'server', '主板'),
    tile('nvme', 'drive', 'NVMe'),
    tile('other', 'array', '其它'),
  ].filter(Boolean);
  return {
    data: {
      // 无任何传感器 = 合法真值：空磁贴 + 空温度墙（回退 mock 会显示假温度）
      tiles,
      wall: items.map((t) => ({ label: t.label || t.key, tempC: Math.round(t.celsius) })),
    },
    live: true,
  };
}

/** 历史序列（SysHistView 直调，不经 useViewData）
 * @param {string} dim cpu|mem|temp|net|disk|gpu
 * @param {string} rangeKey '24h'|'7d'|'30d'
 * @returns {Promise<{data: {series: number[], labels: string[], stats: {avg: string, max: string, n: number}}|null, live: boolean}>} */
export async function fetchHistorySeries(dim, rangeKey) {
  try {
    const resp = await getHistory(rangeKey);
    const rows = resp.points ?? [];
    // 历史落库为 UTC 无时区后缀（契约 §2.3），补 Z 按 UTC 解析再转本地显示，
    // 否则图表横轴比本机时间慢 8 小时（真机 UTC+8 实测）
    const labels = rows.map((p) => {
      const d = new Date(`${p.ts}Z`);
      if (Number.isNaN(d.getTime())) return String(p.ts).slice(5, 16).replace('T', ' ');
      const pad = (x) => String(x).padStart(2, '0');
      return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    });
    const field = DIM_FIELDS[dim] ?? 'cpu_avg';
    // 真实值原样入图：mock 时代的 seedShift 固定偏移曾带进真实链路，
    // 让内存/网络/磁盘曲线系统性偏离 WS 读数
    const data = rows.map((p) => Math.round((p[field] ?? 0) * 10) / 10);
    if (!data.length) throw new Error('empty');
    const values = data.filter((v) => v > 0);
    const avg = values.reduce((a, b) => a + b, 0) / (values.length || 1);
    const unit =
      { cpu: '%', mem: ' MB', temp: ' °C', net: ' KB/s', disk: ' KB/s', gpu: '%' }[dim] ?? '';
    return {
      data: {
        series: data,
        labels,
        stats: {
          avg: `${avg.toFixed(1)}${unit}`,
          max: `${Math.max(...values).toFixed(1)}${unit}`,
          n: rows.length,
        },
      },
      live: true,
    };
  } catch {
    return { data: null, live: false };
  }
}

/** 系统页四张图表：4 个 history 序列 + realtime 内存总量并发取（此前串行瀑布 5×RTT）
 * @returns {Promise<{data: {labels: string[], cpuSeries: object[], memSeries: object[], netSeries: object[], diskSeries: object[]}|null, live: boolean}>} */
export async function fetchSystemCharts() {
  const [cpuS, memS, netS, diskS, snapS] = await Promise.allSettled([
    fetchHistorySeries('cpu', '24h'),
    fetchHistorySeries('mem', '24h'),
    fetchHistorySeries('net', '24h'),
    fetchHistorySeries('disk', '24h'),
    getRealtime(),
  ]);
  const resp = pick(cpuS);
  if (!resp?.live) return { data: null, live: false };
  const resp2 = pick(memS);
  const resp3 = pick(netS);
  const resp4 = pick(diskS);
  const labels = resp.data.labels;
  const mk = (r, name, color, extra = {}) => ({
    name,
    color,
    data: r?.data?.series ?? [],
    ...extra,
  });
  const memTotalMb = pick(snapS)?.mem_total_mb ?? null;
  const memPct = (r2) =>
    memTotalMb
      ? (r2?.data?.series ?? []).map((mb) => Math.round((mb / memTotalMb) * 1000) / 10)
      : (r2?.data?.series ?? []);
  return {
    data: {
      labels,
      cpuSeries: [mk(resp, 'CPU', '#F15A2C')],
      memSeries: [mk(resp2, '内存', '#5B9CF6', { data: memPct(resp2) })],
      // 后端历史只有全网聚合 net_kbps，无按网卡/上下行序列——不虚构 per-NIC 线
      netSeries: [mk(resp3, '总吞吐', '#3FB68B')],
      // 后端历史暂只聚合 disk_read_kbps，写序列缺数据源——只画「读」，不拿读冒充写
      diskSeries: [mk(resp4, '读', '#F15A2C')],
    },
    live: true,
  };
}

/** 历史区间统计（SysHistView 直调；§3.1 stats）
 * @param {string} dim cpu|mem|temp|net|disk|gpu
 * @param {string} rangeKey '24h'|'7d'|'30d'
 * @returns {Promise<{avg: string, max: string, n: number, live: boolean}|null>} */
export async function fetchHistoryStats(dim, rangeKey) {
  try {
    const data = await getHistoryStats(dim, rangeKey);
    const unit =
      { cpu: '%', mem: ' MB', temp: ' °C', net: ' KB/s', disk: ' KB/s', gpu: '%' }[dim] ?? '';
    return {
      avg: data.avg != null ? `${Number(data.avg).toFixed(1)}${unit}` : '—',
      max: data.max != null ? `${Number(data.max).toFixed(1)}${unit}` : '—',
      n: data.n,
      live: true,
    };
  } catch {
    return null;
  }
}
