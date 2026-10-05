'use strict';

/**
 * 总览（Dashboard）视图适配层：8 路并发数据源 → 磁贴形状。
 * 实时快照合并函数（apply*Realtime）同时服务首载与 WS/轮询聚合（DashView watch）。
 */

import * as mock from '../mock';
import { getRealtime, getTemperatures } from '../api/endpoints/monitor';
import { getRaid, getVolumes } from '../api/endpoints/storage';
import { getDocker, getSystemInfo } from '../api/endpoints/system';
import { getFans } from '../api/endpoints/control';
import { getFiringEvents } from '../api/endpoints/alert';
import { hhmm, pick } from './shared';

/** 内存分量格式化：<1GB 用 MB，其余 GB（free(1) 风格） */
function memSize(mb) {
  if (mb == null) return '—';
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`;
}

/** 总览页数据形状（与 mock.dashboard 同形状的契约；模板/WS 合并零改动）
 * @typedef {object} DashboardData
 * @property {{percent: number, cores: number[], freqPerCore: (number|null)[], freqMaxMhz: number|null, coresText: string, freqGHz: number|null, tempC: number|null}} cpu
 * @property {{percent: number, usedText: string, totalText: string, availText: string, buffersText: string, cachedText: string, reservedText: string}} mem
 * @property {{rxText: string, rxValue: string, rxUnit: string, txText: string}} net
 * @property {{readText: string, readValue: string, readUnit: string, writeText: string}} diskIo
 * @property {{total: string, usedPercent: number, usedText: string, status: string, level: string, check: string}} array
 * @property {{percent: number, tempC: number|null, vramText: string}} gpu
 * @property {{watts: number|string, cpuW: number|string, dramW: number|string}} power
 * @property {string|null} dockerText
 * @property {any} storageSummary
 * @property {{uptime: string, uptimeDays: string, uptimeRest: string, osVersion: string, loadText: string, processCount: number|null}} system
 * @property {{name: string, percent: number, vramText: string, engineText: string, freqText: string, tempC: number|string|null, watts: number|string, driverText: string}} gpuDetail
 * @property {Array<{name: string, chip: string, rpm: number, dutyPercent: number, tempC: number, durSec: number}>} fans
 * @property {Array<{name: string, statText?: string, exited?: boolean}>} dockerBrief
 * @property {Array<{label: string, tempC: number}>} diskTemps
 * @property {{label: string, percent: number, usedText: string, tempC: string}} cache
 * @property {{label: string, percent: number, usedText: string, syncText: string}} cloud
 * @property {Array<{level: 'bad'|'warn', text: string, time: string, jump: {path: string, action: string}}>} [activeAlerts]
 */

/**
 * live 形态的磁贴骨架：与 mock.dashboard 同形状但全空值。
 * fetchDashboard 从骨架出发只填真实数据——「mock 深拷贝 + 条件覆盖」会让
 * 无 RAID/无 GPU/无温度源的机器残留演示值被当成读数。
 * @returns {DashboardData}
 */
export function emptyDashboard() {
  return {
    cpu: {
      percent: 0,
      cores: [],
      freqPerCore: [],
      freqMaxMhz: null,
      coresText: '—',
      freqGHz: null,
      tempC: null,
    },
    mem: {
      percent: 0,
      usedText: '—',
      totalText: '—',
      availText: '—',
      buffersText: '—',
      cachedText: '—',
      reservedText: '—',
    },
    net: { rxText: '—', rxValue: '—', rxUnit: '', txText: '—' },
    diskIo: { readText: '—', readValue: '—', readUnit: '', writeText: '—' },
    array: {
      total: '—',
      usedPercent: 0,
      usedText: '未检测到阵列',
      status: '—',
      level: '—',
      check: '—',
    },
    gpu: { percent: 0, tempC: null, vramText: '显存 —' },
    power: { watts: '—', cpuW: '—', dramW: '—' },
    dockerText: null,
    storageSummary: null,
    system: {
      uptime: '—',
      uptimeDays: '—',
      uptimeRest: '',
      osVersion: '—',
      loadText: '—',
      processCount: null,
    },
    gpuDetail: {
      name: 'GPU',
      percent: 0,
      vramText: '—',
      engineText: '—',
      freqText: '—',
      tempC: null,
      watts: '—',
      driverText: '—',
    },
    fans: [],
    dockerBrief: [],
    diskTemps: [],
    cache: { label: '缓存卷', percent: 0, usedText: '—', tempC: '—' },
    cloud: { label: '数据卷', percent: 0, usedText: '—', syncText: '—' },
  };
}

/** 把实时快照的内存分量并入内存磁贴（首载与 WS 聚合共用；后端直读 /proc/meminfo + 5s 缓存）。
 * 已使用 = 总大小 − 可用；系统保留 = 已使用 − (缓冲+缓存) 的正差额（契约 §2.1，后端算好） */
export function applyMemRealtime(mem, snap) {
  mem.percent = snap.mem_percent;
  mem.usedText = memSize(snap.mem_used_mb);
  mem.totalText = memSize(snap.mem_total_mb);
  mem.availText = memSize(snap.mem_available_mb);
  mem.buffersText = memSize(snap.mem_buffers_mb);
  mem.cachedText = memSize(snap.mem_cached_mb);
  mem.reservedText = memSize(snap.mem_reserved_mb);
}

/** 把实时快照的每核占用/频率并入 CPU 磁贴数据（首载与 WS 聚合共用，契约 §2.1） */
export function applyCpuRealtime(cpu, snap) {
  if (Array.isArray(snap.cpu_per_core) && snap.cpu_per_core.length) {
    cpu.cores = snap.cpu_per_core;
  }
  cpu.freqPerCore = Array.isArray(snap.cpu_freq_per_core) ? snap.cpu_freq_per_core : [];
  if (snap.cpu_freq_max_mhz) cpu.freqMaxMhz = snap.cpu_freq_max_mhz;
  const freqs = cpu.freqPerCore.filter((v) => v > 0);
  if (freqs.length) cpu.freqGHz = Math.round(Math.max(...freqs) / 10) / 100;
  else if (snap.cpu_freq_mhz) cpu.freqGHz = Math.round(snap.cpu_freq_mhz / 10) / 100;
}

/** 把实时快照的 GPU 分量并入总览 GPU 磁贴（契约 §2.1 gpu 对象；无卡不覆盖） */
export function applyGpuRealtime(gpu, snap) {
  const g = snap.gpu;
  if (!g || !g.available) return;
  if (g.percent != null) gpu.percent = Math.round(g.percent);
  if (g.temp_c != null) gpu.tempC = Math.round(g.temp_c);
  // intel_gpu_top 不提供显存：缺失时显式置“—”，避免残留演示值被当成真实读数
  gpu.vramText =
    g.vram_used_mb != null && g.vram_total_mb
      ? `显存 ${(g.vram_used_mb / 1024).toFixed(1)} GB`
      : '显存 —';
}

/** GPU 详情卡：intel_gpu_top 帧（频率/包功耗/引擎占用）；显存无内核接口恒“—”。
 * Gen9 的 Video 引擎承担编解码（转码）、VideoEnhance 负责增强/缩放 */
export function applyGpuDetail(detail, snap) {
  const g = snap.gpu;
  if (!g || !g.available) return;
  detail.name = (g.name || '').replace(/^Intel Corporation /, '') || detail.name;
  detail.percent = Math.round(g.percent ?? 0);
  detail.tempC = g.temp_c != null ? Math.round(g.temp_c) : '—';
  detail.vramText = '—';
  const dec = g.video_busy;
  const enc = g.enhance_busy;
  detail.engineText =
    dec == null && enc == null
      ? '—'
      : `转码 ${Math.round(dec ?? 0)}% · 增强 ${Math.round(enc ?? 0)}%`;
  const actual = g.freq_mhz;
  const requested = g.freq_max_mhz;
  detail.freqText =
    !actual && !requested
      ? '待机 (RC6)'
      : `${Math.round(actual ?? 0)} / ${Math.round(requested ?? 0)} MHz`;
  detail.watts = g.power_w != null ? Math.round(g.power_w * 10) / 10 : '—';
}

/** 把实时快照的 RAPL 功耗并入功耗磁贴（后端 energy_uj 差分；无 RAPL 平台显示 —） */
export function applyPowerRealtime(power, snap) {
  const p = snap.power;
  if (!p || !p.available) {
    power.watts = '—';
    power.cpuW = '—';
    power.dramW = '—';
    return;
  }
  power.watts = Math.round((p.watts ?? 0) * 10) / 10;
  power.cpuW = Math.round((p.cpu_w ?? 0) * 10) / 10;
  power.dramW = p.dram_w == null ? '—' : Math.round(p.dram_w * 10) / 10;
}

/** 把实时快照的系统分量并入系统磁贴（首载与 WS/轮询聚合共用；osVersion 需 info 接口，另处回填） */
export function applySystemRealtime(system, snap) {
  const days = Math.floor(snap.uptime_s / 86400);
  const hours = Math.floor((snap.uptime_s % 86400) / 3600);
  system.uptimeDays = String(days);
  system.uptimeRest = `天 ${hours} 小时`;
  system.uptime = `${days} 天 ${hours} 小时`;
  const load = Array.isArray(snap.load) ? snap.load : [];
  system.loadText = load.map((x) => x.toFixed(2)).join(' / ') || '—';
  system.processCount = snap.process_count;
}

// ---------------- 吞吐量口径与格式化（网络/磁盘磁贴共用） ----------------

/** 合成接口（不承载独立外部流量，求和时剔除） */
const SYNTHETIC_NET_RE = /^(ovs-system$|docker0$|br-|veth)/;

/** 实时吞吐求和口径：剔除 OVS 系统口/veth/docker 桥；物理口 X 与其 OVS 内部口
 * X-ovs 并存时只计物理口——OVS 环境下两份计数器是同一份流量，不剔会双计 */
export function realNetIfaces(net) {
  const names = Object.keys(net ?? {});
  return names
    .filter((n) => !SYNTHETIC_NET_RE.test(n))
    .filter((n) => {
      if (!n.endsWith('-ovs')) return true;
      return !names.includes(n.slice(0, -4));
    });
}

/** 吞吐量自适应单位：KB/s 起步，≥1MB/s 升 MB/s，≥1GB/s 升 GB/s。
 * 空闲流量常在个位数 KB/s，固定 MB/s 会恒显示 0.0（看起来像没采到数据） */
export function throughputParts(kbps) {
  const v = Number(kbps) || 0;
  if (v >= 1024 ** 2) return { value: (v / 1024 ** 2).toFixed(1), unit: 'GB/s' };
  if (v >= 1024) return { value: (v / 1024).toFixed(1), unit: 'MB/s' };
  return { value: v >= 100 ? v.toFixed(0) : v.toFixed(1), unit: 'KB/s' };
}

export function throughputText(kbps) {
  const p = throughputParts(kbps);
  return `${p.value} ${p.unit}`;
}

/** 把实时快照的网络吞吐并入磁贴（首载与 WS/轮询聚合共用） */
export function applyNetRealtime(net, snap) {
  const ifaces = realNetIfaces(snap.net);
  const rxTotal = ifaces.reduce((a, n) => a + (snap.net[n].rx_kbps ?? 0), 0);
  const txTotal = ifaces.reduce((a, n) => a + (snap.net[n].tx_kbps ?? 0), 0);
  const [main] = [...ifaces].sort(
    (a, b) =>
      snap.net[b].rx_kbps + snap.net[b].tx_kbps - (snap.net[a].rx_kbps + snap.net[a].tx_kbps)
  );
  const rx = throughputParts(rxTotal);
  net.rxText = `${rx.value} ${rx.unit} ↓`;
  net.rxValue = rx.value;
  net.rxUnit = `${rx.unit} ↓`;
  net.txText = `↑ ${throughputText(txTotal)} · ${main ?? 'eth0'}`;
}

/** 把实时快照的磁盘 IO 并入磁贴（首载与 WS/轮询聚合共用） */
export function applyDiskRealtime(diskIo, snap) {
  const io = snap.disk_io ?? {};
  const r = throughputParts(io.read_kbps ?? 0);
  diskIo.readText = `${r.value} ${r.unit} 读`;
  diskIo.readValue = r.value;
  diskIo.readUnit = `${r.unit} 读`;
  diskIo.writeText = `↑ 写 ${throughputText(io.write_kbps ?? 0)}`;
}

/** 总览页取数：realtime 不可达整页演示回退，个别源缺失由骨架空值兜底
 * @returns {Promise<{data: DashboardData, live: boolean}>} */
export async function fetchDashboard() {
  const [snapS, tempsS, raidS, dockerS, infoS, eventsS, fansS, volsS] = await Promise.allSettled([
    getRealtime(),
    getTemperatures(),
    getRaid(),
    getDocker(),
    getSystemInfo(),
    getFiringEvents(),
    getFans(),
    getVolumes(),
  ]);
  const snap = pick(snapS);
  if (!snap) return { data: mock.dashboard, live: false };

  const temps = pick(tempsS) ?? [];
  const raid = pick(raidS);
  const docker = pick(dockerS);
  const info = pick(infoS);
  const events = pick(eventsS) ?? [];
  const zones = pick(fansS) ?? [];
  const mounts = pick(volsS) ?? [];

  const logical = snap.cpu_per_core.length || 1;
  const cpuTemp = temps.filter((t) => t.zone === 'cpu');
  // 骨架出发只填真实数据；各数据源缺失时段保持骨架空值（「—」），不残留演示值
  const d = emptyDashboard();

  d.cpu.percent = Math.round(snap.cpu_percent * 10) / 10;
  applyCpuRealtime(d.cpu, snap);
  d.cpu.coresText = `${logical} 线程 · 负载 ${snap.load?.[0] ?? '—'}`;
  d.cpu.tempC = cpuTemp.length ? Math.max(...cpuTemp.map((t) => t.celsius)) : null;

  d.mem.percent = snap.mem_percent;
  applyMemRealtime(d.mem, snap);
  applyGpuRealtime(d.gpu, snap);
  applyGpuDetail(d.gpuDetail, snap);

  applyNetRealtime(d.net, snap);
  applyDiskRealtime(d.diskIo, snap);
  applyPowerRealtime(d.power, snap);
  applySystemRealtime(d.system, snap);

  const allVols = [...(raid?.hardware_raid ?? []), ...(raid?.software_raid ?? [])];
  if (allVols.length) {
    const vol = allVols[0];
    d.array.status = vol.healthy ? '运行中' : vol.state;
    d.array.level = `${vol.source === 'storcli' ? '硬 RAID' : '软 RAID'} ${vol.level} · ${vol.name}`;
    d.array.usedText = `状态 ${vol.state}`;
    d.array.usedPercent = vol.healthy ? 100 : 0;
    // 真实容量（软 RAID 来自 mdstat blocks×1024）；缺失显式“—”，不残留演示值
    d.array.total = Number.isFinite(vol.size_bytes)
      ? `${(vol.size_bytes / 1e12).toFixed(1)} TB`
      : '—';
  }

  d.system.osVersion =
    info?.fnos_version ||
    [info?.platform, info?.kernel].filter(Boolean).join(' ') ||
    d.system.osVersion;

  d.fans = zones.length
    ? zones.map((z, i) => ({
        name: z.name,
        chip: z.mode === 'auto' ? 'AUTO' : 'PWM',
        rpm: z.current_rpm ?? 0,
        dutyPercent: Math.round(z.current_pwm_pct ?? 0),
        tempC: z.sensor_temp_c != null ? Math.round(z.sensor_temp_c) : 0,
        durSec: 3 + (i % 3) * 0.35,
      }))
    : []; // 未配置风区时空列表，模板走空态，不回退演示风扇

  const containers = docker?.containers ?? [];
  if (containers.length) {
    const running = containers.filter((c) => c.state === 'running').length;
    d.dockerText = `${running} 运行中 · ${containers.length - running} 退出`;
    d.dockerBrief = containers
      .slice(0, 6)
      .map((c) =>
        c.state === 'running'
          ? { name: c.name, statText: c.status }
          : { name: c.name, exited: true }
      );
  }

  // 机械盘 SMART 温度 + 每块 NVMe 取 Composite 一条（Sensor 1/2 与 Composite 同源）
  const diskTemps = [
    ...temps.filter((t) => t.zone === 'disk'),
    ...temps.filter(
      (t) => t.zone === 'nvme' && (t.label || '').toLowerCase().includes('composite')
    ),
  ];
  if (diskTemps.length) {
    d.diskTemps = diskTemps
      .slice(0, 6)
      .map((t) => ({ label: t.label || t.key, tempC: Math.round(t.celsius) }));
  }

  // 存储卷卡：ssd 标记的挂载为缓存卷，其余最大卷为数据卷；无“云盘备份”数据源不虚构
  if (mounts.length) {
    const sizeText = (bytes) =>
      bytes >= 1e12 ? `${(bytes / 1e12).toFixed(1)} TB` : `${(bytes / 1e9).toFixed(0)} GB`;
    const fill = (block, m, prefix) => {
      block.label = `${prefix} ${m.mount} · ${(m.fs_type || '').toUpperCase()}`;
      block.percent = Math.round(m.percent ?? 0);
      block.usedText = `已用 ${sizeText(m.used_bytes ?? 0)} / ${sizeText(m.total_bytes ?? 0)}`;
      block.tempC = '—'; // 卷接口无温度；nvme 温度在盘温卡展示
    };
    const ssd = mounts.find((m) => (m.opts ?? []).includes('ssd'));
    const dataVol = mounts
      .filter((m) => !(m.opts ?? []).includes('ssd') && m.mount.startsWith('/vol'))
      .sort((a, b) => (b.total_bytes ?? 0) - (a.total_bytes ?? 0))[0];
    if (ssd) fill(d.cache, ssd, '缓存');
    if (dataVol) {
      fill(d.cloud, dataVol, '数据卷');
      d.cloud.syncText = '实时';
    }
    d.storageSummary = `${mounts.length} 卷已挂载`;
  }

  if (events.length) {
    d.activeAlerts = events.slice(0, 2).map((e) => ({
      level: e.severity === 'critical' ? 'bad' : 'warn',
      text: e.message || e.rule_name,
      time: hhmm(e.fired_at),
      jump: { path: '/nasdeck/automation', action: '查看告警' },
    }));
  }
  return { data: d, live: true };
}
