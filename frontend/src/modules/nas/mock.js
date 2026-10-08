'use strict';

/**
 * nasdeck UNRAID 界面 mock 数据集。
 * 本次仅做界面（不调后端），数据形状向 docs/前后端数据接口约定.md 的字段风格靠拢
 * （snake_case、*_c 温度、*_percent 百分比、*_kbps 速率），后续接真实接口时逐域替换。
 */

/** UNRAID 稿图表色板 */
export const colors = {
  acc: '#F15A2C',
  ok: '#3FB68B',
  info: '#5B9CF6',
  purp: '#A077E8',
  warn: '#ECA43C',
  temp: '#E8734B',
  gpu: '#C291F0',
};

/** 顶部导航分组（页签：总览｜存储｜监控｜服务｜系统）。不设静态角标：
 * 硬盘/Docker/告警数量随真机变化，写死即假数据 */
export const navGroups = [
  { items: [{ path: '/nasdeck/dash', title: '总览', icon: 'dash' }] },
  {
    items: [
      { path: '/nasdeck/storage', title: '存储卷', icon: 'array' },
      { path: '/nasdeck/disks', title: '硬盘', icon: 'drive' },
    ],
  },
  {
    items: [
      { path: '/nasdeck/detect', title: '硬件', icon: 'cpu' },
      { path: '/nasdeck/system', title: '系统', icon: 'pulse' },
      { path: '/nasdeck/temps', title: '温度', icon: 'temp' },
      { path: '/nasdeck/sys-hist', title: '趋势', icon: 'hist' },
      { path: '/nasdeck/scope', title: '示波器', icon: 'power' },
    ],
  },
  {
    items: [
      { path: '/nasdeck/docker', title: 'Docker', icon: 'docker' },
      { path: '/nasdeck/ports', title: '端口', icon: 'net' },
      { path: '/nasdeck/fan', title: '风扇', icon: 'fan' },
    ],
  },
  {
    items: [
      { path: '/nasdeck/timeline', title: '事件', icon: 'clock' },
      { path: '/nasdeck/automation', title: '自动化', icon: 'shield' },
      { path: '/nasdeck/manual', title: '手册', icon: 'book' },
      { path: '/nasdeck/about', title: '关于', icon: 'info' },
    ],
  },
];

/** 总览页八磁贴 + 附属卡 */
export const dashboard = {
  cpu: {
    percent: 23,
    cores: [31, 18, 44, 12, 26, 38, 9, 22],
    freqPerCore: [4600, 4500, 3800, 4300, 1200, 800, 4700, 3900],
    freqMaxMhz: 4700,
    coresText: '4C8T · 负载 0.42',
    freqGHz: 3.49,
    tempC: 45,
  },
  mem: {
    percent: 41,
    usedText: '26.2 GB',
    totalText: '64.0 GB',
    availText: '40.1 GB',
    buffersText: '412 MB',
    cachedText: '21.4 GB',
    reservedText: '4.4 GB',
  },
  net: { rxText: '12.3 MB/s ↓', rxValue: '12.3', rxUnit: 'MB/s ↓', txText: '↑ 3.1 MB/s · eth0' },
  diskIo: {
    readText: '86 MB/s 读',
    readValue: '86',
    readUnit: 'MB/s 读',
    writeText: '↑ 写 42 MB/s',
  },
  array: {
    total: '21.8 TB',
    usedPercent: 38,
    usedText: '已用 8.2 TB · 38%',
    status: '运行中',
    level: 'RAID 6 · 4+0 盘',
    check: '校验：无活动',
  },
  gpu: { percent: 15, tempC: 44, vramText: '显存 0.9 GB' },
  power: { watts: 40.5, cpuW: 32.1, dramW: 8.4 },
  dockerText: '3 运行中 · 1 退出',
  storageSummary: '3 卷已挂载',
  system: {
    uptime: '23 天 4 小时',
    uptimeDays: '23',
    uptimeRest: '天 4 小时',
    osVersion: '0.9.20',
    loadText: '0.42 / 0.38 / 0.35',
    processCount: 217,
  },
  gpuDetail: {
    name: 'Intel HD Graphics P530',
    percent: 15,
    vramText: '0.9 / 1.7 GB',
    engineText: '编码 12% · 解码 3%',
    freqText: '850 / 1150 MHz',
    tempC: 44,
    watts: 6.8,
    driverText: 'i915 · QuickSync',
  },
  fans: [
    { name: 'CPU_FAN', chip: 'PWM', rpm: 1220, dutyPercent: 46, tempC: 45, durSec: 3.7 },
    { name: '前板_FAN', chip: 'DC', rpm: 980, dutyPercent: 38, tempC: 38, durSec: 4.1 },
    { name: '后板_FAN', chip: 'PWM', rpm: 1450, dutyPercent: 52, tempC: 61, durSec: 3.4 },
  ],
  dockerBrief: [
    { name: 'plex', statText: '3.4% · 1.2 GB' },
    { name: 'qBittorrent', statText: '1.1% · 420 MB' },
    { name: 'homeassistant', statText: '0.8% · 660 MB' },
    { name: 'memcached', exited: true },
  ],
  diskTemps: [
    { label: '盘位 1 · 4 TB', tempC: 34 },
    { label: '盘位 2 · 4 TB', tempC: 35 },
    { label: '盘位 3 · 8 TB', tempC: 47 },
    { label: '盘位 4 · 8 TB', tempC: 39 },
    { label: '盘位 5 · SSD', tempC: 41 },
    { label: '阵列卡', tempC: 36 },
  ],
  cache: { label: '缓存 nvme0n1 · Btrfs', percent: 64, usedText: '308 / 480 GB', tempC: '41 °C' },
  cloud: {
    label: '云盘 backup · OSS',
    percent: 32,
    usedText: '6.4 / 20 TB',
    syncText: '今日 04:00 同步',
  },
};

/** 活动告警（总览 / 通知下拉 / 自动化页共用） */
export const activeAlerts = [
  {
    level: 'warn',
    text: '盘位 3 SMART 05 重映射扇区数增长（12 → 13），建议关注或安排更换',
    time: '10:21',
    jump: { path: '/nasdeck/disks', action: '查看硬盘' },
  },
  {
    level: 'warn',
    text: '机箱后部温度 61 °C 超过阈值 60 °C，已持续 5 分钟',
    time: '10:32',
    jump: { path: '/nasdeck/temps', action: '查看温度' },
  },
];

/** 通知渠道（自动化页渠道管理演示回退；config_masked 形状与 GET /alert/channels 一致） */
export const alertChannels = [
  {
    id: 1,
    name: '手机 Bark',
    type: 'bark',
    enabled: true,
    config_masked: { device_key: 'AbCd****', server: 'https://api.day.app' },
  },
  {
    id: 2,
    name: '运维邮箱',
    type: 'email',
    enabled: true,
    config_masked: {
      host: 'smtp.example.com',
      port: '587',
      username: 'a***@example.com',
      password: '****',
      to: 'o***@example.com',
    },
  },
  {
    id: 3,
    name: '家庭 webhook',
    type: 'webhook',
    enabled: false,
    config_masked: { url: 'http://192.168.1.5:8080/hook' },
  },
];

/** 巡检计划演示回退：缺省关闭态（不虚构"上周已跑"，last_run=null 如实） */
export const selftestSchedule = {
  enabled: false,
  weekday: 6,
  hour: 4,
  type: 'short',
  last_run: null,
};

/** 告警规则（自动化页规则列表演示回退，形状与 AlertRuleItem 一致） */
export const alertRules = [
  {
    id: 1,
    name: '规则 · 温度',
    metric: 'temp_max',
    comparator: '>',
    threshold: 60,
    duration_ticks: 12,
    severity: 'warning',
    channel_ids: [1, 2],
    actions: [],
    enabled: true,
  },
  {
    id: 2,
    name: '规则 · SMART 属性',
    metric: 'disk_failed',
    comparator: '>',
    threshold: 0,
    duration_ticks: 1,
    severity: 'critical',
    channel_ids: [1],
    actions: ['fan_full'],
    enabled: true,
  },
];

/** 存储卷页 */
/** 存储卷页（与 live 适配层同形状：devices 新字段 + topology 真实层级演示） */
export const storage = {
  array: {
    name: 'md126',
    level: 'RAID 6',
    totalText: '总容量 20.0 TB',
    membersText: '软阵列 (mdadm) · 成员 4 盘',
    activityText: '无重建 / 校验活动',
    running: true,
  },
  arrayController: null,
  devices: [
    {
      name: 'sda',
      model: 'WDC WD40EFRX',
      slot: null,
      role: 'RAID 成员',
      alias: null,
      fsText: null,
      tempC: 34,
      readText: '—',
      writeText: '—',
      usagePercent: null,
      usageClass: null,
      capacityText: '4 TB · SN EFRX',
      status: '正常',
    },
    {
      name: 'sdb',
      model: 'WDC WD40EFRX',
      slot: null,
      role: 'RAID 成员',
      alias: null,
      fsText: null,
      tempC: 35,
      readText: '—',
      writeText: '—',
      usagePercent: null,
      usageClass: null,
      capacityText: '4 TB · SN 8P2K',
      status: '正常',
    },
    {
      name: 'sdc',
      model: 'Seagate ST8000VN0022',
      slot: null,
      role: 'RAID 成员',
      alias: null,
      fsText: null,
      tempC: 47,
      readText: '—',
      writeText: '—',
      usagePercent: null,
      usageClass: null,
      capacityText: '8 TB · SMART 05 警告',
      status: '警告 (05)',
    },
    {
      name: 'sdd',
      model: 'Seagate ST8000VN0022',
      slot: null,
      role: 'RAID 成员',
      alias: null,
      fsText: null,
      tempC: 39,
      readText: '—',
      writeText: '—',
      usagePercent: null,
      usageClass: null,
      capacityText: '8 TB · SN ZAD1',
      status: '正常',
    },
    {
      name: 'nvme0n1',
      model: 'Samsung PM883',
      slot: null,
      role: null,
      alias: '系统盘',
      fsText: 'BTRFS',
      tempC: 41,
      readText: '—',
      writeText: '—',
      usagePercent: 9,
      usageClass: 'c-ok',
      capacityText: '480 GB · SN S45N',
      status: '正常',
    },
  ],
  volume: {
    name: '/',
    usedText: '42.6 / 476 GB',
    percent: 9,
    fs: 'Btrfs',
    mount: '/',
  },
  dataVolume: {
    name: '/vol1',
    usedText: '6.4 / 20.0 TB',
    percent: 32,
    fs: 'BTRFS',
  },
  topology: {
    controller: { mode: 'soft', model: null },
    arrays: [
      {
        key: 'md126',
        name: 'md126',
        levelText: 'RAID 6',
        sizeText: '20.0 TB',
        state: 'clean',
        healthy: true,
        source: 'mdadm',
        members: [
          {
            label: 'sda2',
            model: null,
            sizeText: '4 TB',
            state: null,
            hotspare: null,
            failed: false,
          },
          {
            label: 'sdb2',
            model: null,
            sizeText: '4 TB',
            state: null,
            hotspare: null,
            failed: false,
          },
          {
            label: 'sdc2',
            model: null,
            sizeText: '8 TB',
            state: null,
            hotspare: null,
            failed: false,
          },
          {
            label: 'sdd2',
            model: null,
            sizeText: '8 TB',
            state: null,
            hotspare: null,
            failed: false,
          },
        ],
        volume: { mount: '/vol1', fs: 'btrfs', usedText: '6.4 / 20.0 TB', percent: 32 },
      },
    ],
    standalone: [
      {
        name: 'nvme0n1',
        model: 'Samsung PM883',
        sizeText: '480 GB',
        alias: '系统盘',
        health: 'passed',
        tempC: 41,
        partitions: [
          { name: 'nvme0n1p1', fstype: 'vfat', sizeText: '0.5 GB', mountpoint: '/boot/efi' },
          { name: 'nvme0n1p2', fstype: 'btrfs', sizeText: '476 GB', mountpoint: '/' },
        ],
      },
    ],
  },
};

/** 事件时间线演示回退（形状与 AlertEventItem 一致；倒序混排规则/系统事件） */
export const timeline = [
  {
    id: 3,
    rule_id: null,
    rule_name: '日志哨兵',
    metric: 'log_alert',
    value: null,
    threshold: null,
    severity: 'warning',
    status: 'resolved',
    message: 'blk_update_request: I/O error, dev sdb, sector 12345',
    fired_at: '2026-01-05T02:12:00+00:00',
    resolved_at: '2026-01-05T02:12:00+00:00',
  },
  {
    id: 2,
    rule_id: 1,
    rule_name: '规则 · 温度',
    metric: 'temp_max',
    value: 61.5,
    threshold: 60,
    severity: 'warning',
    status: 'resolved',
    message: '温度超阈值后回落',
    fired_at: '2026-01-04T14:03:00+00:00',
    resolved_at: '2026-01-04T14:31:00+00:00',
  },
  {
    id: 1,
    rule_id: null,
    rule_name: 'SMART 周期巡检',
    metric: 'selftest',
    value: null,
    threshold: null,
    severity: 'info',
    status: 'resolved',
    message: 'sda short 巡检 → completed',
    fired_at: '2026-01-04T04:07:00+00:00',
    resolved_at: '2026-01-04T04:07:00+00:00',
  },
];

/** 硬盘 SMART 页 */
export const disks = {
  list: [
    {
      slot: 1,
      model: 'WDC WD40EFRX',
      capacity: '4 TB',
      rpm: '5400',
      tempC: 34,
      hours: '18240 h',
      health: '正常',
      oracle: {
        score: 92,
        grade: 'good',
        has_history: true,
        dims: [
          { key: 'reallocated', value: 100 },
          { key: 'pending', value: 100 },
          { key: 'media', value: 100 },
          { key: 'temp', value: 92 },
          { key: 'wear', value: 65 },
        ],
        etas: [],
      },
    },
    {
      slot: 2,
      model: 'WDC WD40EFRX',
      capacity: '4 TB',
      rpm: '5400',
      tempC: 35,
      hours: '18238 h',
      health: '正常',
    },
    {
      slot: 3,
      model: 'Seagate ST8000VN0022',
      capacity: '8 TB',
      rpm: '7200',
      tempC: 47,
      hours: '29511 h',
      health: '警告 (05)',
      oracle: {
        score: 71,
        grade: 'watch',
        has_history: true,
        dims: [
          { key: 'reallocated', value: 55 },
          { key: 'pending', value: 100 },
          { key: 'media', value: 100 },
          { key: 'temp', value: 52 },
          { key: 'wear', value: 44 },
        ],
        etas: [{ metric: 'reallocated', days: 20, current: 8, threshold: 10, slope_per_day: 0.1 }],
      },
    },
    {
      slot: 5,
      model: 'Samsung PM883',
      capacity: '480 G',
      rpm: 'SSD',
      tempC: 41,
      hours: '9310 h',
      health: '正常',
    },
  ],
  selftest: { label: '盘位 3 · 短自检（B）', percent: 62 },
};

/**
 * 硬盘 SMART 趋势演示序列（仅后端不可达的演示回退；确定性阶梯+正弦扰动，非真实数据）。
 * 形状与后端 SmartTrendResponse 一致（契约 §3.2），points 按天铺 ~45 点。
 * @param {string} device
 * @param {string} metric
 * @param {number} [days]
 * @returns {{ device: string, metric: string, granularity: '1h'|'1d', days: number, points: Array<{ts: string, value: number, raw_text: string|null}> }}
 */
export function smartTrendDemo(device, metric, days = 30) {
  const base =
    {
      reallocated: 4,
      pending: 1,
      uncorrectable: 0,
      wear_leveling: 91,
      percent_used: 37,
      media_errors: 12,
      temp_c: 38,
      power_on_hours: 18240,
    }[metric] ?? 0;
  const step =
    {
      reallocated: 0.04,
      pending: 0.02,
      uncorrectable: 0,
      wear_leveling: -0.03,
      percent_used: 0.05,
      media_errors: 0.04,
      temp_c: 0.1,
      power_on_hours: 12,
    }[metric] ?? 0;
  const n = 45;
  const start = Date.now() - n * 24 * 3600 * 1000;
  const points = Array.from({ length: n }, (_, i) => {
    const jitter = Math.round(Math.sin(i * 1.7) * 10) / 10; // 确定性扰动（不闪变）
    const value = Math.round((base + step * i + jitter * (step === 0 ? 1 : 0.4)) * 10) / 10;
    return {
      ts: new Date(start + i * 24 * 3600 * 1000).toISOString().slice(0, 19),
      value: Math.max(0, value),
      raw_text: null,
    };
  });
  return { device, metric, granularity: '1h', days, points };
}

/** 硬件检测页 */
export const detect = {
  system: [
    ['操作系统', 'fnOS 0.9.20'],
    ['内核', '6.1.0-x86_64'],
    ['运行时长', '23 天 4 小时'],
    ['负载 (1/5/15m)', '0.42 / 0.38 / 0.35'],
  ],
  board: [
    ['厂商', 'Supermicro'],
    ['型号', 'X11SSH-LN4F'],
    ['BIOS', '2.4 · 2023-06-01'],
    ['主板温度', '38 °C'],
  ],
  cpu: {
    rows: [
      ['型号', 'Xeon E3-1245 v5'],
      ['核心 / 线程', '4 核 8 线程'],
      ['实时频率', '3.49 GHz'],
      ['温度 / 使用率', '45 °C · 23%'],
    ],
    cores: [31, 18, 44, 12, 26, 38, 9, 22],
  },
  dimms: [
    {
      slot: 'DIMM_A1',
      size: '16 GB',
      detail: {
        容量: '16 GB',
        类型: 'DDR4 ECC',
        频率: '2400 MT/s',
        通道: 'A',
        厂商: 'Samsung',
        序列号: '31D8C4A0',
        状态: '正常',
        可校正错误: '0',
      },
    },
    {
      slot: 'DIMM_A2',
      size: '16 GB',
      detail: {
        容量: '16 GB',
        类型: 'DDR4 ECC',
        频率: '2400 MT/s',
        通道: 'A',
        厂商: 'Samsung',
        序列号: '31D8C4A1',
        状态: '正常',
        可校正错误: '0',
      },
    },
    {
      slot: 'DIMM_B1',
      size: '16 GB',
      detail: {
        容量: '16 GB',
        类型: 'DDR4 ECC',
        频率: '2400 MT/s',
        通道: 'B',
        厂商: 'Samsung',
        序列号: '31D8C4A2',
        状态: '正常',
        可校正错误: '0',
      },
    },
    { slot: 'DIMM_B2', size: '空', empty: true },
  ],
  network: [
    ['eth0', { up: true, text: '1000 Mb · 192.168.1.10' }],
    ['eth1', { up: false, text: '未连接' }],
    ['eth2', { up: false, text: '未连接' }],
    ['eth3', { up: false, text: '未连接' }],
  ],
  raid: {
    rows: [
      ['型号', 'LSI 9361-8i'],
      ['固件', '4.680.00'],
      ['BBU', '正常'],
      ['温度', '36 °C'],
    ],
    chips: ['CC 调度：关', '热备：无', 'CopyBack：开'],
  },
  diskSlots: [
    { slot: '盘位 1', size: '4 TB', desc: '正常 · 34 °C' },
    { slot: '盘位 2', size: '4 TB', desc: '正常 · 35 °C' },
    { slot: '盘位 3', size: '8 TB', desc: '警告 · 47 °C', warn: true },
    { slot: '盘位 4', size: '8 TB', desc: '正常 · 39 °C' },
    { slot: '盘位 5', size: 'SSD 480G', desc: '正常 · 41 °C' },
    { slot: '盘位 6', size: '空', desc: '—', empty: true },
  ],
  diskChips: ['网络唤醒 WoL：开', '盘定位：关'],
  env: {
    runtime: [
      ['Python', '3.12.7'],
      ['监听端口', '9800（仅回环）'],
      ['日志级别', 'INFO'],
      ['原始数据保留', '120 分钟'],
    ],
    tools: [
      {
        name: 'smartctl',
        desc: '硬盘 SMART 读取',
        ok: true,
        path: '/usr/bin/smartctl',
        install: '',
      },
      {
        name: 'sensors',
        desc: '温度/风扇/电压传感',
        ok: true,
        path: '/usr/bin/sensors',
        install: '',
      },
      { name: 'mdadm', desc: '软 RAID 阵列状态', ok: true, path: '/usr/sbin/mdadm', install: '' },
      {
        name: 'dmidecode',
        desc: '主板/内存条信息',
        ok: true,
        path: '/usr/sbin/dmidecode',
        install: '',
      },
      { name: 'decode-dimms', desc: '内存温度', ok: false, path: '', install: 'i2c-tools' },
      { name: 'ethtool', desc: '网卡信息与 WOL', ok: true, path: '/usr/bin/ethtool', install: '' },
    ],
    drivers: [
      { name: 'nct6775', desc: '风扇芯片驱动（Nuvoton 新机型）', loaded: true },
      { name: 'it87', desc: '风扇芯片驱动（ITE 旧机型）', loaded: false },
    ],
    storcli: { ok: true, path: '/usr/local/bin/storcli64', desc: 'LSI MegaRAID/HBA 阵列卡工具' },
  },
};

/** 温度监控页 */
export const temps = {
  tiles: [
    { key: 'tcpu', icon: 'cpu', label: 'CPU', tempC: 45 },
    { key: 'tboard', icon: 'server', label: '主板', tempC: 38 },
    { key: 'tnvme', icon: 'drive', label: 'NVMe', tempC: 41 },
    { key: 'traid', icon: 'array', label: '阵列卡', tempC: 36 },
  ],
  wall: [
    { label: 'CPU Package', tempC: 45 },
    { label: 'CPU Core 1', tempC: 44 },
    { label: 'CPU Core 3', tempC: 52 },
    { label: '主板', tempC: 38 },
    { label: 'PCH', tempC: 41 },
    { label: 'NVMe 盘 5', tempC: 41 },
    { label: '阵列卡', tempC: 36 },
    { label: '盘 1', tempC: 34 },
    { label: '盘 3', tempC: 47 },
    { label: '机箱后部', tempC: 61 },
    { label: '进风', tempC: 28 },
    { label: 'PSU', tempC: 33 },
  ],
};

/** 机箱热力图（花活 F）演示回退：与 fetchChassis 输出同形（board/dimms/nics/sensors/fans/disks）。
 * board 取 QEMU——立体机箱（三期 R）演示自动落到 virtual 逻辑视图 */
export const chassis = {
  board: {
    vendor: 'Supermicro',
    model: 'X11SCH-F',
    product_name: 'X11SCH-F',
    cpuName: 'Intel Xeon E-2124',
  },
  dimms: 2,
  nics: 1,
  sensors: [
    { key: 'm:pkg', label: 'CPU Package', zone: 'cpu', celsius: 45, grade: 'normal' },
    { key: 'm:core1', label: 'Core 1', zone: 'cpu', celsius: 44, grade: 'normal' },
    { key: 'm:core3', label: 'Core 3', zone: 'cpu', celsius: 52, grade: 'normal' },
    { key: 'm:pch', label: 'PCH', zone: 'board', celsius: 41, grade: 'normal' },
    { key: 'm:board', label: '主板', zone: 'board', celsius: 38, grade: 'normal' },
    { key: 'm:nvme', label: 'NVMe 盘 5', zone: 'nvme', celsius: 41, grade: 'normal' },
    { key: 'm:raid', label: '阵列卡', zone: 'other', celsius: 36, grade: 'normal' },
    { key: 'm:rear', label: '机箱后部', zone: 'other', celsius: 61, grade: 'hot' },
    { key: 'm:intake', label: '进风', zone: 'other', celsius: 28, grade: 'normal' },
    { key: 'm:psu', label: 'PSU', zone: 'other', celsius: 33, grade: 'normal' },
  ],
  fans: [
    { id: 1, name: 'CPU_FAN', rpm: 1220, duty: 46 },
    { id: 2, name: '前板_FAN', rpm: 980, duty: 38 },
    { id: 3, name: '后板_FAN', rpm: 1450, duty: 52 },
  ],
  disks: [
    {
      slot: 1,
      device: 'sda',
      model: 'WDC WD40EFRX',
      capacity: '4 TB',
      tempC: 34,
      health: '正常',
      kind: 'HDD',
      serial: null,
    },
    {
      slot: 2,
      device: 'sdb',
      model: 'WDC WD40EFRX',
      capacity: '4 TB',
      tempC: 35,
      health: '正常',
      kind: 'HDD',
      serial: null,
    },
    {
      slot: 3,
      device: 'sdc',
      model: 'Seagate ST8000VN0022',
      capacity: '8 TB',
      tempC: 47,
      health: '警告 (05)',
      kind: 'HDD',
      serial: null,
    },
    {
      slot: 5,
      device: 'sdd',
      model: 'Samsung PM883',
      capacity: '480 G',
      tempC: 41,
      health: '正常',
      kind: 'SSD',
      serial: null,
    },
  ],
};

/** 跑分演示成绩（花活二期 Q；fetchBenchHistory 后端不可达时回退） */
export const benchHistory = [
  {
    id: 3,
    device: 'sdc',
    seconds: 20,
    duty: 30,
    avg_mbps: 142.3,
    peak_mbps: 158.7,
    bytes_read: 2983,
    direct: true,
    created_at: '2026-10-08T21:40:00',
    curve: [
      { t: 0.5, mbps: 138.2 },
      { t: 1, mbps: 149.6 },
      { t: 1.5, mbps: 155.1 },
      { t: 2, mbps: 158.7 },
      { t: 2.5, mbps: 141.9 },
    ],
  },
  {
    id: 2,
    device: 'sda',
    seconds: 20,
    duty: 30,
    avg_mbps: 118.6,
    peak_mbps: 131.4,
    bytes_read: 2486,
    direct: true,
    created_at: '2026-10-08T21:30:00',
    curve: [
      { t: 0.5, mbps: 112.0 },
      { t: 1, mbps: 124.5 },
      { t: 1.5, mbps: 131.4 },
      { t: 2, mbps: 118.8 },
    ],
  },
];

/** 网络星图演示聚合（花活二期 L；UNetMap 后端不可达时回退） */
export const networkMap = {
  listening: 12,
  established: 9,
  lan: 7,
  wan: 2,
  remotes: [
    { ip: '192.168.31.12', lan: true, count: 3 },
    { ip: '192.168.31.240', lan: true, count: 2 },
    { ip: '223.5.5.5', lan: false, count: 1 },
  ],
};

/** 容器 24h 趋势演示序列（花活二期 M；后端不可达时 fetchContainerTrend 回退） */
export function dockerTrendDemo(name, hours = 24) {
  const n = Math.min(hours * 60, 400);
  const points = [];
  const t0 = Date.now() - n * 60000;
  for (let i = 0; i < n; i += 1) {
    const wave = Math.sin(i / 23) * 1.6 + Math.sin(i / 7) * 0.7;
    points.push({
      ts: new Date(t0 + i * 60000).toISOString().slice(0, 19),
      cpu_percent: Math.max(0.2, 3 + wave),
      mem_mb: 420 + Math.sin(i / 40) * 60,
      read_kbps: Math.max(0, 40 + wave * 18),
      write_kbps: Math.max(0, 12 + Math.cos(i / 15) * 8),
    });
  }
  return { name, hours, points };
}

/** Docker 页 */
export const docker = {
  containers: [
    {
      name: 'plex',
      image: 'plexinc/pms-docker:latest',
      av: 'P',
      avClass: 'c4',
      running: true,
      statusText: 'Up 6 days',
      mem: '1.2 GB',
      memBytes: 1.2 * 1024 ** 3,
      cpu: '3.4%',
      cpuPercent: 3.4,
      readBps: 2.1 * 1024 ** 2,
      writeBps: 0.4 * 1024 ** 2,
      ports: '32400→32400',
      up: '6 天',
    },
    {
      name: 'qBittorrent',
      image: 'linuxserver/qbittorrent:latest',
      av: 'q',
      avClass: 'c1',
      running: true,
      statusText: 'Up 2 days',
      mem: '420 MB',
      memBytes: 420 * 1024 ** 2,
      cpu: '1.1%',
      cpuPercent: 1.1,
      readBps: 8.9 * 1024 ** 2,
      writeBps: 1.2 * 1024 ** 2,
      ports: '6881→6881',
      up: '2 天',
    },
    {
      name: 'homeassistant',
      image: 'homeassistant/home-assistant:stable',
      av: 'h',
      avClass: 'c3',
      running: true,
      statusText: 'Up 23 days',
      mem: '660 MB',
      memBytes: 660 * 1024 ** 2,
      cpu: '0.8%',
      cpuPercent: 0.8,
      readBps: 0.1 * 1024 ** 2,
      writeBps: 0.1 * 1024 ** 2,
      ports: '8123→8123',
      up: '23 天',
    },
    {
      name: 'memcached',
      image: 'memcached:alpine',
      av: 'm',
      avClass: 'c2',
      running: false,
      statusText: 'Exited (0) 3 days ago',
      mem: '—',
      memBytes: null,
      cpu: '—',
      cpuPercent: null,
      readBps: null,
      writeBps: null,
      ports: '—',
      up: '—',
    },
  ],
};

/** 端口占用页 */
export const ports = {
  list: [
    {
      app: 'nasdeck 面板',
      av: 'n',
      avClass: 'c1',
      port: 9821,
      proto: 'TCP',
      process: 'uvicorn (2103)',
      reach: 'ok',
      reachText: '可达',
      searchText: 'nasdeck 面板 9821 uvicorn 2103 tcp 可达',
      confirm: '确认释放端口 9821？将向进程 uvicorn 发送 SIGTERM。',
    },
    {
      app: 'Plex',
      av: 'P',
      avClass: 'c4',
      port: 32400,
      proto: 'TCP',
      process: 'Plex Media Server (2210)',
      reach: 'ok',
      reachText: '可达',
      searchText: 'plex 32400 plex media server 2210 tcp 可达',
      confirm: '确认释放端口 32400？将向进程 Plex Media Server 发送 SIGTERM。',
    },
    {
      app: 'SMB',
      av: 'S',
      avClass: 'c2',
      port: 445,
      proto: 'TCP',
      process: 'smbd (1201)',
      reach: 'warn',
      reachText: '受限（仅局域网）',
      searchText: 'smb 445 smbd 1201 tcp 受限 仅局域网',
      confirm: '确认释放端口 445？系统服务释放前需特别确认。',
      danger: true,
    },
    {
      app: '未知',
      av: '?',
      avClass: 'c1',
      port: 9090,
      proto: 'TCP',
      process: 'python3 (3321)',
      reach: 'err',
      reachText: '不可达',
      searchText: '未知 9090 python3 3321 tcp 不可达',
      confirm: '确认释放端口 9090？',
    },
  ],
};

/** 风扇控制页 */
export const fans = {
  takeover: true,
  cards: [
    {
      id: 1,
      name: 'CPU_FAN',
      rpm: 1220,
      duty: 46,
      pwm: true,
      mode: 'curve',
      curveId: 1,
      sensorKey: 'coretemp:Package id 0',
      sensorTempC: 45,
    },
    {
      id: 2,
      name: '前板_FAN',
      rpm: 980,
      duty: 38,
      pwm: false,
      mode: 'auto',
      curveId: null,
      sensorKey: null,
      sensorTempC: null,
    },
    {
      id: 3,
      name: '后板_FAN',
      rpm: 1450,
      duty: 52,
      pwm: true,
      mode: 'fixed',
      curveId: null,
      sensorKey: null,
      sensorTempC: null,
    },
  ],
  /** 调速依据候选（形状与 /monitor/temperatures 条目一致，仅演示回退用） */
  sensors: [
    {
      key: 'coretemp:Package id 0',
      chip: 'coretemp',
      label: 'Package id 0',
      celsius: 45,
      zone: 'cpu',
      grade: 'normal',
    },
    {
      key: 'coretemp:Core 1',
      chip: 'coretemp',
      label: 'Core 1',
      celsius: 44,
      zone: 'cpu',
      grade: 'normal',
    },
    {
      key: 'coretemp:Core 3',
      chip: 'coretemp',
      label: 'Core 3',
      celsius: 52,
      zone: 'cpu',
      grade: 'normal',
    },
    { key: 'acpitz:1', chip: 'acpitz', label: '1', celsius: 38, zone: 'board', grade: 'normal' },
    {
      key: 'pch:Composite',
      chip: 'pch',
      label: 'Composite',
      celsius: 41,
      zone: 'board',
      grade: 'normal',
    },
    {
      key: 'nvme0:Composite',
      chip: 'nvme',
      label: 'nvme0 Composite',
      celsius: 41,
      zone: 'nvme',
      grade: 'normal',
    },
    { key: 'smart:sda', chip: 'smart', label: 'sda', celsius: 34, zone: 'disk', grade: 'normal' },
    { key: 'smart:sdb', chip: 'smart', label: 'sdb', celsius: 35, zone: 'disk', grade: 'normal' },
  ],
  curveDefault: [
    [30, 22],
    [38, 35],
    [46, 50],
    [55, 68],
    [62, 85],
  ],
  rules: [
    {
      title: '规则 A（CPU 传感器）',
      sensor: 'CPU Package',
      curve: '曲线 1（静音优先）',
      hysteresis: '3 °C',
    },
    {
      title: '规则 B（硬盘传感器）',
      sensor: '盘位 3',
      curve: '曲线 2（散热优先）',
      hysteresis: '4 °C',
    },
  ],
};

/** 操作手册页 */
export const manual = {
  toc: [
    { text: '1. 快速上手' },
    { text: '1.1 安装与首次配置', lv2: true },
    { text: '1.2 数据源说明', lv2: true },
    { text: '2. 页面说明' },
    { text: '2.1 硬件检测', lv2: true },
    { text: '2.2 系统资源 / 温度', lv2: true },
    { text: '2.3 硬盘 / 存储卷', lv2: true },
    { text: '2.4 风扇控制', lv2: true },
    { text: '3. 常见问题' },
    { text: '4. 版本与更新' },
  ],
};

/** 关于页 */
export const about = {
  version: 'dev-0.0.6',
  desc: '飞牛 fnOS 硬件监控面板 · UNRAID 风格',
  slogan: '把要 SSH 才能看的硬件状态，装进一块面板',
  build: [
    ['构建时间', '2026-09-29 08:00'],
    ['Git 提交', '03f4846'],
    ['许可', 'MIT'],
    ['反馈渠道', 'GitHub Issues'],
  ],
};
