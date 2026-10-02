'use strict';

/**
 * 契约数据 → 视图数据 适配层。
 * 每个视图一个异步取数函数，返回与 mock.js 同形状的数据 + live 标记：
 * - 后端可达且有数据 → 真实值（live: true）
 * - 接口失败 / 数据源缺失（如 Windows 无温度传感器）→ 回退演示值（live: false）
 * 视图经 useViewData 消费，模板零改动。
 */

import { apiBase, apiData } from './client';
import * as mock from '../mock';

/** 秒 → HH:MM */
function hhmm(iso) {
  const t = new Date(iso);
  return isNaN(t)
    ? ''
    : `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`;
}

/** 内存分量格式化：<1GB 用 MB，其余 GB（free(1) 风格） */
function memSize(mb) {
  if (mb == null) return '—';
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`;
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

function pick(settled) {
  return settled.status === 'fulfilled' ? settled.value : null;
}

async function safe(path, opts) {
  try {
    return await apiData(path, opts);
  } catch {
    return null;
  }
}

// ---------------- 总览 ----------------

/**
 * live 形态的磁贴骨架：与 mock.dashboard 同形状但全空值。
 * fetchDashboard 从骨架出发只填真实数据——「mock 深拷贝 + 条件覆盖」会让
 * 无 RAID/无 GPU/无温度源的机器残留演示值被当成读数。
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
    array: { total: '—', usedPercent: 0, usedText: '未检测到阵列', status: '—', level: '—', check: '—' },
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

export async function fetchDashboard() {
  const [snapS, tempsS, raidS, dockerS, infoS, eventsS, fansS, volsS] = await Promise.allSettled([
    apiData('/api/v1/monitor/realtime'),
    apiData('/api/v1/monitor/temperatures'),
    apiData('/api/v1/storage/raid'),
    apiData('/api/v1/system/docker/containers'),
    apiData('/api/v1/system/info'),
    apiData('/api/v1/alert/events?limit=5&status=firing'),
    apiData('/api/v1/control/fans'),
    apiData('/api/v1/storage/volumes'),
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

function uptimeText(seconds) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return days ? `${days} 天 ${hours} 小时` : `${hours} 小时`;
}

export async function fetchActiveAlerts() {
  const events = await safe('/api/v1/alert/events?limit=5&status=firing');
  if (events === null) return { data: mock.activeAlerts, live: false }; // 后端不可达才演示
  // 空列表 = 无告警，是合法真值，必须如实展示（回退 mock 会让铃铛恒显假告警）
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

// ---------------- 存储卷 ----------------

/** live 形态骨架：无阵列/无盘/无卷时段保持空值，由模板空态兜底（不残留演示阵列） */
export function emptyStorage() {
  return {
    array: null,
    devices: [],
    volume: null,
    dataVolume: null,
    arrayController: null,
  };
}

export async function fetchStorage() {
  const [raidS, disksS, volsS] = await Promise.allSettled([
    apiData('/api/v1/storage/raid'),
    apiData('/api/v1/storage/disks'),
    apiData('/api/v1/storage/volumes'),
  ]);
  const raid = pick(raidS);
  const disks = pick(disksS);
  const vols = pick(volsS);
  // 三源全不可达才整页演示回退；个别源缺失保持骨架空值
  if (!raid && !disks && !vols) return { data: mock.storage, live: false };

  const d = emptyStorage();
  const allVols = [...(raid?.hardware_raid ?? []), ...(raid?.software_raid ?? [])];
  if (allVols.length) {
    const vol = allVols[0];
    const cardDrives = raid?.drives ?? [];
    const hotspares = cardDrives.filter((x) => x.hotspare).length;
    d.array = {
      name: vol.name,
      level: `RAID ${vol.level}`,
      totalText: vol.size_bytes
        ? `总容量 ${Math.round((vol.size_bytes / 1024 ** 4) * 10) / 10} TB`
        : '容量未知',
      membersText: [
        raid?.controller?.model || (vol.source === 'storcli' ? '硬件阵列卡' : '软阵列 (mdadm)'),
        cardDrives.length ? `成员 ${cardDrives.filter((x) => !x.hotspare).length} 盘` : null,
        hotspares ? `热备 ${hotspares}` : null,
      ]
        .filter(Boolean)
        .join(' · '),
      activityText:
        raid?.controller?.cachevault && raid.available
          ? `CacheVault ${raid.controller.cachevault_status ?? ''}`.trim()
          : '无重建 / 校验活动',
      running: vol.healthy,
    };
  }

  if (disks?.length) {
    d.devices = disks.map((disk, i) => ({
      name: disk.device,
      model: disk.model || disk.device,
      slot: i + 1,
      fs: disk.alias || '物理盘',
      tempC: disk.temp_c != null ? Math.round(disk.temp_c) : null,
      readText: '—',
      writeText: '—',
      meterPercent: 100,
      meterClass:
        disk.health === 'failing' ? 'c-bad' : disk.health === 'warning' ? 'c-warn' : 'c-ok',
      capacityText: `${disk.size_human}${disk.serial ? ` · SN ${String(disk.serial).slice(-4)}` : ''}`,
      status:
        { passed: '正常', warning: '警告', failing: '故障', unknown: '未知' }[disk.health] ??
        '未知',
    }));
  }

  const mainVol =
    (vols ?? []).filter((v) => v.mount === '/' || v.mount === 'C:\\')[0] ?? (vols ?? [])[0];
  if (mainVol) {
    d.volume = {
      name: mainVol.mount,
      usedText: `${Math.round((mainVol.used_bytes / 1024 ** 4) * 10) / 10} / ${Math.round((mainVol.total_bytes / 1024 ** 4) * 10) / 10} TB`,
      percent: mainVol.percent,
      fs: mainVol.fs_type,
      mount: mainVol.mount,
    };
  }
  // 数据卷卡：最大 /vol 挂载（fnOS 数据卷）；后端无「云盘备份」数据源，不虚构云盘
  const dataVol = (vols ?? [])
    .filter((v) => (v.mount || '').startsWith('/vol'))
    .sort((a, b) => (b.total_bytes ?? 0) - (a.total_bytes ?? 0))[0];
  if (dataVol) {
    d.dataVolume = {
      name: dataVol.mount,
      usedText: `${Math.round((dataVol.used_bytes / 1024 ** 4) * 10) / 10} / ${Math.round((dataVol.total_bytes / 1024 ** 4) * 10) / 10} TB`,
      percent: dataVol.percent,
      fs: (dataVol.fs_type || '').toUpperCase(),
    };
  }
  if (raid?.controller) {
    d.arrayController = {
      model: String(raid.controller.model || '').split(' [')[0] || raid.controller.model,
      mode: raid.controller.mode || (raid.available ? 'mega' : 'hba'),
      driver: raid.controller.driver,
      cachevault: raid.controller.cachevault,
      cachevaultStatus: raid.controller.cachevault_status,
      note: raid.controller.note,
    };
  }
  return { data: d, live: true };
}

// ---------------- 硬盘 SMART ----------------

export async function fetchDisks() {
  const [disksS, testsS] = await Promise.allSettled([
    apiData('/api/v1/storage/disks'),
    apiData('/api/v1/storage/self-tests'),
  ]);
  const disks = pick(disksS);
  if (!disks?.length) return { data: mock.disks, live: false };

  const tests = pick(testsS) ?? [];
  const running = tests.find((t) => t.status === 'running');
  const d = {
    list: disks.map((disk, i) => ({
      slot: i + 1,
      device: disk.device,
      model: disk.model || disk.device,
      capacity: disk.size_human,
      rpm: disk.rotational ? 'HDD' : 'SSD',
      tempC: disk.temp_c != null ? Math.round(disk.temp_c) : null,
      hours: disk.power_on_hours != null ? `${disk.power_on_hours} h` : '—',
      health:
        { passed: '正常', warning: '警告', failing: '故障', unknown: '未知' }[disk.health] ??
        '未知',
      serial: disk.serial,
    })),
    // 无进行中自检 = 合法真值：置 null 由视图隐藏区块（回退 mock 会显示假进度条）
    selftest: running
      ? { device: running.device, label: `${running.device} · ${running.type}`, percent: running.percent ?? 0 }
      : null,
  };
  return { data: d, live: true };
}

// ---------------- 系统资源（图表序列） ----------------

const DIM_FIELDS = {
  cpu: 'cpu_avg',
  mem: 'mem_avg_mb',
  temp: 'temp_max_c',
  net: 'net_avg_kbps',
  disk: 'disk_read_kbps',
  gpu: 'gpu_avg',
};

export async function fetchHistorySeries(dim, rangeKey) {
  const minutes = { '24h': 1440, '7d': 10080, '30d': 43200 }[rangeKey] ?? 10080;
  const points = { '24h': 144, '7d': 168, '30d': 360 }[rangeKey] ?? 168;
  try {
    const resp = await apiData(`/api/v1/monitor/history?minutes=${minutes}&points=${points}`);
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

export async function fetchSystemCharts() {
  const resp = await fetchHistorySeries('cpu', '24h');
  if (!resp.live) return { data: null, live: false };
  const resp2 = await fetchHistorySeries('mem', '24h');
  const resp3 = await fetchHistorySeries('net', '24h');
  const resp4 = await fetchHistorySeries('disk', '24h');
  const labels = resp.data.labels;
  const mk = (r, name, color, extra = {}) => ({
    name,
    color,
    data: r?.data?.series ?? [],
    ...extra,
  });
  const [snapS] = await Promise.allSettled([apiData('/api/v1/monitor/realtime')]);
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

// ---------------- 温度 ----------------

export async function fetchTemps() {
  const items = await safe('/api/v1/monitor/temperatures');
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

// ---------------- Docker ----------------

export async function fetchDocker() {
  const resp = await safe('/api/v1/system/docker/containers');
  if (resp === null) return { data: mock.docker, live: false }; // 后端不可达才演示
  const avClasses = ['c1', 'c2', 'c3', 'c4'];
  return {
    data: {
      // docker 不可用或 0 容器都是合法真值：空列表 + 不可用原因（extra），不回退假容器
      containers: (resp.containers ?? []).map((c, i) => ({
        name: c.name,
        av: (c.name[0] || '?').toUpperCase(),
        avClass: avClasses[i % 4],
        running: c.state === 'running',
        mem: c.mem_usage ?? '—',
        cpu: c.cpu_percent != null ? `${c.cpu_percent}%` : '—',
        net: '—',
        ports: c.ports[0] ?? '—',
        up: c.status,
      })),
      available: !!resp.available,
      reason: resp.reason ?? null,
    },
    live: true,
    extra: resp.available ? null : resp.reason ?? 'docker 不可用',
  };
}

// ---------------- 端口 ----------------

export async function fetchPorts() {
  const entries = await safe('/api/v1/system/ports');
  if (entries === null) return { data: mock.ports, live: false }; // 后端不可达才演示
  const listens = entries.filter((p) => p.status === 'LISTEN').slice(0, 20);
  const avClasses = ['c1', 'c2', 'c3', 'c4'];
  return {
    data: {
      // 0 监听 = 合法真值：空列表，不回退演示端口
      list: listens.map((p, i) => ({
        app: p.alias || p.process || `${p.local_port}`,
        av: String(p.alias || p.process || '?')[0].toUpperCase(),
        avClass: avClasses[i % 4],
        port: p.local_port,
        proto: p.proto.toUpperCase(),
        process: `${p.process ?? '未知'} (${p.pid ?? '—'})`,
        pid: p.pid,
        reach: p.remote_addr ? 'warn' : 'ok',
        reachText: p.remote_addr ? '有外部连接' : '监听中',
        searchText: `${p.alias ?? ''} ${p.local_port} ${p.process ?? ''} ${p.proto}`.toLowerCase(),
        confirm: `确认终止进程 ${p.process ?? p.pid}（占用 ${p.local_port} 端口）？`,
        danger: false,
      })),
    },
    live: true,
  };
}

// ---------------- 风扇 ----------------

/** 曲线编辑器缺省模板（后端无曲线时的预填形状；明确是模板，取自 mock 数据集会让
 * 首次「保存」把演示形状写成真实默认曲线） */
const DEFAULT_CURVE_TEMPLATE = [
  [30, 22],
  [38, 35],
  [46, 50],
  [55, 68],
  [62, 85],
];

export async function fetchFans() {
  const [zonesS, curvesS, fcsS, chansS] = await Promise.allSettled([
    apiData('/api/v1/control/fans'),
    apiData('/api/v1/control/curves'),
    apiData('/api/v1/control/fcs'),
    apiData('/api/v1/control/hwmon/channels'),
  ]);
  const zones = pick(zonesS);
  if (zones === null) return { data: mock.fans, live: false }; // 仅后端不可达才演示回退

  const curves = pick(curvesS);
  const fcs = pick(fcsS);
  const channels = pick(chansS) ?? [];
  const firstCurve = (curves ?? [])[0];
  return {
    data: {
      takeover: fcs?.taken_over || zones.some((z) => z.mode !== 'auto'),
      cards: zones.slice(0, 6).map((z) => ({
        id: z.id,
        name: z.name,
        rpm: z.current_rpm ?? 0,
        duty: Math.round(z.current_pwm_pct ?? 0),
        pwm: z.mode !== 'auto',
        hwmonName: z.hwmon_name,
        pwmChannel: z.pwm_channel,
        fanChannel: z.fan_channel,
      })),
      // 未建风区的硬件通道（检测区数据源）；已建风区的通道在卡片区展示
      channels: channels.filter(
        (c) => !zones.some((z) => z.hwmon_name === c.chip && z.pwm_channel === c.pwm_channel)
      ),
      curveDefault: firstCurve?.points?.length ? firstCurve.points : DEFAULT_CURVE_TEMPLATE,
      curveMeta: firstCurve
        ? {
            name: firstCurve.name,
            hysteresis_c: firstCurve.hysteresis_c,
            ramp_per_tick: firstCurve.ramp_per_tick,
          }
        : null,
      curveId: firstCurve?.id ?? null,
    },
    live: true,
  };
}

// ---------------- 自动化 / 关于 ----------------

export async function fetchAutomation() {
  const [eventsS, activeS, chansS] = await Promise.allSettled([
    apiData('/api/v1/alert/events?limit=10'),
    fetchActiveAlerts(),
    apiData('/api/v1/alert/channels'),
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

export async function fetchAbout() {
  const info = await safe('/api/v1/system/info');
  if (!info) return { data: mock.about, live: false };
  return {
    data: {
      version: info.app_version ?? mock.about.version,
      desc: `飞牛 fnOS 硬件监控面板 · ${info.platform} ${info.kernel}`,
      slogan: mock.about.slogan,
      build: [
        ['主机名', info.hostname || '—'],
        ['内核', info.kernel || '—'],
        ['Python', info.python || '—'],
        ['fnOS', info.fnos_version || '非 fnOS 环境'],
      ],
    },
    live: true,
  };
}

// ---------------- 硬件检测（§3.7 /hardware 只读） ----------------

/** live 形态骨架：未检测到的硬件分区保持空（空 RAID 卡不显示演示 LSI 卡） */
function emptyDetect() {
  return {
    system: [],
    board: [],
    cpu: { rows: [], cores: [] },
    dimms: [],
    network: [],
    raid: { rows: [], chips: [] },
    diskSlots: [],
    diskChips: [],
    env: { runtime: [], schemes: [], tools: [], drivers: [], storcli: { ok: false, path: '', desc: '' } },
  };
}

export async function fetchDetect() {
  const [hwS, infoS, disksS, envS] = await Promise.allSettled([
    apiData('/api/v1/hardware'),
    apiData('/api/v1/system/info'),
    apiData('/api/v1/storage/disks'),
    apiData('/api/v1/system/env'),
  ]);
  const hw = pick(hwS);
  if (!hw || !Object.keys(hw).length) return { data: mock.detect, live: false };
  const info = pick(infoS);
  const disks = pick(disksS) ?? [];
  const env = pick(envS);

  const d = emptyDetect();
  const kv = (rows) => rows.filter(Boolean);

  if (env) {
    // 运行环境自检（§2.14）：安装期自举结果（工具/驱动/storcli/生效配置）
    d.env = {
      runtime: kv([
        ['Python', env.python?.version],
        [
          '监听端口',
          env.config?.host === '127.0.0.1'
            ? `${env.config.port}（仅回环）`
            : String(env.config?.port),
        ],
        ['日志级别', env.config?.log_level],
        [
          '原始数据保留',
          env.config?.raw_keep_minutes != null ? `${env.config.raw_keep_minutes} 分钟` : null,
        ],
      ]),
      schemes: env.schemes ?? [],
      tools: env.tools ?? [],
      drivers: env.drivers ?? [],
      storcli: env.storcli ?? { ok: false, path: '', desc: '' },
    };
  }

  if (info) {
    d.system = kv([
      ['操作系统', info.fnos_version ? `fnOS ${info.fnos_version}` : info.platform],
      ['内核', info.kernel],
      ['运行时长', uptimeText(info.uptime_s)],
      ['主机名', info.hostname],
    ]);
  }
  if (hw.board?.available) {
    const bios = [hw.board.bios_vendor, hw.board.bios_version].filter(Boolean).join(' ');
    d.board = kv([
      ['厂商', hw.board.vendor],
      ['型号', hw.board.model || hw.board.product_name],
      ['芯片组', hw.board.chipset],
      [
        'BIOS',
        [bios, hw.board.bios_date ? `(${hw.board.bios_date})` : null].filter(Boolean).join(' '),
      ],
    ]);
  }
  if (hw.cpu?.available) {
    d.cpu.rows = kv([
      ['型号', hw.cpu.name],
      ['核心 / 线程', `${hw.cpu.physical_cores ?? '?'} 核 ${hw.cpu.logical_cores ?? '?'} 线程`],
      ['架构', hw.cpu.machine],
    ]);
    d.cpu.cores = [];
    d.cpu.noCores = true;
  }
  if (hw.memory?.available) {
    d.dimms = (hw.memory.dimms ?? []).map((m) => ({
      slot: m.slot,
      size: m.size_mb ? `${m.size_mb} MB` : '空',
      empty: !m.size_mb,
      detail: { 容量: m.size_mb ? `${m.size_mb} MB` : '—', ECC: hw.memory.ecc ? '是' : '否' },
    }));
  }
  if (hw.nic?.available) {
    d.network = (hw.nic.nics ?? []).map((n) => [
      n.name,
      {
        up: !!n.up,
        text: n.up ? `${n.speed_mbps ?? '?'} Mb${n.ipv4 ? ` · ${n.ipv4}` : ''}` : '未连接',
      },
    ]);
  }
  if (hw.raid_card?.available) {
    if (hw.raid_card.mode === 'hba') {
      // HBA 直通卡（如 LSI SAS2308 IT 模式）：无硬 RAID / CacheVault 概念
      d.raid.rows = kv([
        ['型号', hw.raid_card.name],
        ['驱动', hw.raid_card.driver],
        ['模式', 'HBA 直通（IT 模式）'],
      ]);
      d.raid.chips = ['磁盘内核直管', 'SMART 见「硬盘」页', '阵列走软 RAID'];
      d.raid.note = hw.raid_card.note;
    } else {
      d.raid.rows = kv([
        ['型号', hw.raid_card.name],
        ['固件', hw.raid_card.firmware],
        ['CacheVault / BBU', hw.raid_card.cachevault || '未检测到'],
        [
          '卡温度',
          hw.raid_card.controller_temp_c != null ? `${hw.raid_card.controller_temp_c} °C` : null,
        ],
      ]);
      d.raid.chips = [
        `热备：${hw.raid_card.hotspare_count ?? 0} 块`,
        `CopyBack：${
          hw.raid_card.auto_copyback === 'enabled'
            ? '开'
            : hw.raid_card.auto_copyback === 'disabled'
              ? '关'
              : '未知'
        }`,
        `逻辑盘：${hw.raid_card.vd_count ?? 0} · 物理盘：${hw.raid_card.drive_count ?? 0}`,
      ];
    }
  }
  if (disks.length) {
    d.diskSlots = disks.map((disk, i) => ({
      slot: `盘位 ${i + 1} · ${disk.device}`,
      size: disk.size_human,
      desc: `${disk.model || '未知型号'}`,
      warn: disk.health === 'warning' || disk.health === 'failing',
      empty: false,
    }));
    d.diskChips = [`共 ${disks.length} 块物理盘`, '详细 SMART 见「硬盘」页'];
  }
  return { data: d, live: true };
}

/** 历史区间统计（§3.1 stats） */
export async function fetchHistoryStats(dim, rangeKey) {
  const minutes = { '24h': 1440, '7d': 10080, '30d': 43200 }[rangeKey] ?? 10080;
  try {
    const data = await apiData(`/api/v1/monitor/history/stats?minutes=${minutes}&dim=${dim}`);
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

/** 历史报告导出（§3.1 export 文件流），返回可直接下载的 url（带网关 index.cgi 前缀） */
export function historyExportUrl(dim, rangeKey, fmt) {
  const minutes = { '24h': 1440, '7d': 10080, '30d': 43200 }[rangeKey] ?? 10080;
  return `${apiBase()}/api/v1/monitor/history/export?minutes=${minutes}&dim=${dim}&fmt=${fmt}`;
}
