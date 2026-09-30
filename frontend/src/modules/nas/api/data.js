'use strict';

/**
 * 契约数据 → 视图数据 适配层。
 * 每个视图一个异步取数函数，返回与 mock.js 同形状的数据 + live 标记：
 * - 后端可达且有数据 → 真实值（live: true）
 * - 接口失败 / 数据源缺失（如 Windows 无温度传感器）→ 回退演示值（live: false）
 * 视图经 useViewData 消费，模板零改动。
 */

import { apiData } from './client';
import * as mock from '../mock';

/** 秒 → HH:MM */
function hhmm(iso) {
  const t = new Date(iso);
  return isNaN(t)
    ? ''
    : `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`;
}

function gb(mb) {
  return `${(mb / 1024).toFixed(1)} GB`;
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

/** 缺数据段的统一兜底：真值非空用真值，否则演示值 */
function withFallback(value, mockValue) {
  const empty = value === null || value === undefined || (Array.isArray(value) && !value.length);
  return { data: empty ? mockValue : value, live: !empty };
}

// ---------------- 总览 ----------------

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

export async function fetchDashboard() {
  const [snapS, tempsS, raidS, dockerS, infoS, eventsS, fansS] = await Promise.allSettled([
    apiData('/api/v1/monitor/realtime'),
    apiData('/api/v1/monitor/temperatures'),
    apiData('/api/v1/storage/raid'),
    apiData('/api/v1/system/docker/containers'),
    apiData('/api/v1/system/info'),
    apiData('/api/v1/alert/events?limit=5&status=firing'),
    apiData('/api/v1/control/fans'),
  ]);
  const snap = pick(snapS);
  if (!snap) return { data: mock.dashboard, live: false };

  const temps = pick(tempsS) ?? [];
  const raid = pick(raidS);
  const docker = pick(dockerS);
  const info = pick(infoS);
  const events = pick(eventsS) ?? [];
  const zones = pick(fansS) ?? [];

  const logical = snap.cpu_per_core.length || 1;
  const cpuTemp = temps.filter((t) => t.zone === 'cpu');
  const d = JSON.parse(JSON.stringify(mock.dashboard));

  d.cpu.percent = Math.round(snap.cpu_percent * 10) / 10;
  applyCpuRealtime(d.cpu, snap);
  d.cpu.coresText = `${logical} 线程 · 负载 ${snap.load[0] ?? '—'}`;
  d.cpu.tempC = cpuTemp.length ? Math.max(...cpuTemp.map((t) => t.celsius)) : d.cpu.tempC;

  d.mem.percent = snap.mem_percent;
  d.mem.usedText = `已用 ${gb(snap.mem_used_mb)}`;
  d.mem.totalText = `共 ${gb(snap.mem_total_mb)}`;

  const ifaces = Object.entries(snap.net);
  const rxTotal = ifaces.reduce((a, [, v]) => a + v.rx_kbps, 0);
  const txTotal = ifaces.reduce((a, [, v]) => a + v.tx_kbps, 0);
  const main = ifaces[0];
  d.net.rxText = `${(rxTotal / 1024).toFixed(1)} MB/s ↓`;
  d.net.txText = `↑ ${(txTotal / 1024).toFixed(1)} MB/s · ${main ? main[0] : 'eth0'}`;

  d.diskIo.readText = `${((snap.disk_io.read_kbps ?? 0) / 1024).toFixed(0)} MB/s 读`;
  d.diskIo.writeText = `↑ 写 ${((snap.disk_io.write_kbps ?? 0) / 1024).toFixed(0)} MB/s`;

  const allVols = [...(raid?.hardware_raid ?? []), ...(raid?.software_raid ?? [])];
  if (allVols.length) {
    const vol = allVols[0];
    d.array.status = vol.healthy ? '运行中' : vol.state;
    d.array.level = `${vol.source === 'storcli' ? '硬 RAID' : '软 RAID'} ${vol.level} · ${vol.name}`;
    d.array.usedText = `状态 ${vol.state}`;
    d.array.usedPercent = vol.healthy ? 100 : 0;
  }

  d.system.uptime = uptimeText(snap.uptime_s);
  d.system.uptimeS = snap.uptime_s;
  d.system.osVersion =
    info?.fnos_version ||
    [info?.platform, info?.kernel].filter(Boolean).join(' ') ||
    d.system.osVersion;
  d.system.loadText = snap.load.map((x) => x.toFixed(2)).join(' / ') || d.system.loadText;
  d.system.processCount = snap.process_count;

  d.fans = zones.length
    ? zones.map((z, i) => ({
        name: z.name,
        chip: z.mode === 'auto' ? 'AUTO' : 'PWM',
        rpm: z.current_rpm ?? 0,
        dutyPercent: Math.round(z.current_pwm_pct ?? 0),
        tempC: z.sensor_temp_c != null ? Math.round(z.sensor_temp_c) : 0,
        durSec: 3 + (i % 3) * 0.35,
      }))
    : d.fans;

  const containers = docker?.containers ?? [];
  if (containers.length) {
    d.dockerBrief = containers
      .slice(0, 4)
      .map((c) =>
        c.state === 'running'
          ? { name: c.name, statText: c.status }
          : { name: c.name, exited: true }
      );
  }

  const diskTemps = temps.filter((t) => t.zone === 'disk' || t.zone === 'nvme');
  if (diskTemps.length) {
    d.diskTemps = diskTemps
      .slice(0, 6)
      .map((t) => ({ label: t.label || t.key, tempC: Math.round(t.celsius) }));
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
  return withFallback(
    (events ?? []).map((e) => ({
      level: e.severity === 'critical' ? 'bad' : 'warn',
      text: e.message || e.rule_name,
      time: hhmm(e.fired_at),
      jump: { path: '/nasdeck/automation', action: '查看告警' },
    })),
    mock.activeAlerts
  );
}

// ---------------- 存储卷 ----------------

export async function fetchStorage() {
  const [raidS, disksS, volsS] = await Promise.allSettled([
    apiData('/api/v1/storage/raid'),
    apiData('/api/v1/storage/disks'),
    apiData('/api/v1/storage/volumes'),
  ]);
  const raid = pick(raidS);
  const disks = pick(disksS);
  const vols = pick(volsS);
  if (!raid && !disks?.length && !vols?.length) return { data: mock.storage, live: false };

  const d = JSON.parse(JSON.stringify(mock.storage));
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
    selftest: running
      ? { label: `${running.device} · ${running.type}`, percent: running.percent ?? 0 }
      : mock.disks.selftest,
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

export async function fetchHistorySeries(dim, rangeKey, seedShift = 0) {
  const minutes = { '24h': 1440, '7d': 10080, '30d': 43200 }[rangeKey] ?? 10080;
  const points = { '24h': 144, '7d': 168, '30d': 360 }[rangeKey] ?? 168;
  try {
    const resp = await apiData(`/api/v1/monitor/history?minutes=${minutes}&points=${points}`);
    const rows = resp.points ?? [];
    const labels = rows.map((p) => String(p.ts).slice(5, 16).replace('T', ' '));
    const field = DIM_FIELDS[dim] ?? 'cpu_avg';
    const data = rows.map((p) => Math.round(((p[field] ?? 0) + (seedShift % 1)) * 10) / 10);
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
  const [snapLive] = await Promise.allSettled([apiData('/api/v1/monitor/realtime')]);
  const memTotalMb = pick(snapLive)?.mem_total_mb ?? null;
  const resp2 = await fetchHistorySeries('mem', '24h', 0.3);
  const resp3 = await fetchHistorySeries('net', '24h', 0.6);
  const resp4 = await fetchHistorySeries('disk', '24h', 0.9);
  const [snapS] = await Promise.allSettled([apiData('/api/v1/monitor/realtime')]);
  const snap = pick(snapS);
  const labels = resp.data.labels;
  const nics = snap ? Object.keys(snap.net) : ['eth0'];
  const mk = (r, name, color, extra = {}) => ({
    name,
    color,
    data: r?.data?.series ?? [],
    ...extra,
  });
  const memPct = (r2) =>
    memTotalMb
      ? (r2?.data?.series ?? []).map((mb) => Math.round((mb / memTotalMb) * 1000) / 10)
      : (r2?.data?.series ?? []);
  return {
    data: {
      labels,
      cpuSeries: [mk(resp, 'CPU', '#F15A2C')],
      memSeries: [mk(resp2, '内存', '#5B9CF6', { data: memPct(resp2) })],
      netSeriesByNic: Object.fromEntries(
        nics
          .slice(0, 2)
          .map((n) => [
            n,
            [mk(resp3, '下行', '#3FB68B'), mk(resp3, '上行', '#ECA43C', { dash: true })],
          ])
      ),
      diskSeries: [mk(resp4, '读', '#F15A2C'), mk(resp4, '写', '#A077E8')],
      nicNames: nics.slice(0, 2),
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
      tiles: tiles.length ? tiles : mock.temps.tiles,
      wall: items.map((t) => ({ label: t.label || t.key, tempC: Math.round(t.celsius) })),
    },
    live: true,
  };
}

// ---------------- Docker ----------------

export async function fetchDocker() {
  const resp = await safe('/api/v1/system/docker/containers');
  if (!resp?.available || !resp.containers.length) {
    return {
      data: { ...mock.docker, available: resp?.available ?? false, reason: resp?.reason ?? null },
      live: false,
    };
  }
  const avClasses = ['c1', 'c2', 'c3', 'c4'];
  return {
    data: {
      containers: resp.containers.map((c, i) => ({
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
    },
    live: true,
  };
}

// ---------------- 端口 ----------------

export async function fetchPorts() {
  const entries = await safe('/api/v1/system/ports');
  if (!entries?.length) return { data: mock.ports, live: false };
  const listens = entries.filter((p) => p.status === 'LISTEN').slice(0, 20);
  const avClasses = ['c1', 'c2', 'c3', 'c4'];
  return {
    data: {
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

export async function fetchFans() {
  const [zonesS, curvesS, fcsS] = await Promise.allSettled([
    apiData('/api/v1/control/fans'),
    apiData('/api/v1/control/curves'),
    apiData('/api/v1/control/fcs'),
  ]);
  const zones = pick(zonesS);
  const curves = pick(curvesS);
  const fcs = pick(fcsS);
  if (!zones?.length) return { data: mock.fans, live: false };

  const firstCurve = (curves ?? [])[0];
  return {
    data: {
      takeover: fcs?.taken_over || zones.some((z) => z.mode !== 'auto'),
      cards: zones.slice(0, 3).map((z) => ({
        name: z.name,
        rpm: z.current_rpm ?? 0,
        duty: Math.round(z.current_pwm_pct ?? 0),
        pwm: z.mode !== 'auto',
      })),
      curveDefault: firstCurve?.points?.length ? firstCurve.points : mock.fans.curveDefault,
      rules: mock.fans.rules,
      curveId: firstCurve?.id ?? null,
    },
    live: true,
  };
}

// ---------------- 自动化 / 关于 ----------------

export async function fetchAutomation() {
  const events = await safe('/api/v1/alert/events?limit=10');
  const active = await fetchActiveAlerts();
  return {
    data: {
      ...mock.automation,
      activeAlerts: active.data,
      recentEvents: (events ?? []).map((e) => ({
        ...e,
        time: hhmm(e.fired_at),
      })),
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

  const d = JSON.parse(JSON.stringify(mock.detect));
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
    if (!d.dimms.length) d.dimms = mock.detect.dimms;
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

/** 历史报告导出（§3.1 export 文件流），返回可直接下载的 url */
export function historyExportUrl(dim, rangeKey, fmt) {
  const minutes = { '24h': 1440, '7d': 10080, '30d': 43200 }[rangeKey] ?? 10080;
  return `/api/v1/monitor/history/export?minutes=${minutes}&dim=${dim}&fmt=${fmt}`;
}
