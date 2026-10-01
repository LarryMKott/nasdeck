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

/** 顶部导航分组（页签：总览｜存储｜监控｜服务｜系统） */
export const navGroups = [
  { items: [{ path: '/nasdeck/dash', title: '总览', icon: 'dash' }] },
  {
    items: [
      { path: '/nasdeck/storage', title: '存储卷', icon: 'array' },
      { path: '/nasdeck/disks', title: '硬盘', icon: 'drive', badge: 6 },
    ],
  },
  {
    items: [
      { path: '/nasdeck/detect', title: '硬件', icon: 'cpu' },
      { path: '/nasdeck/system', title: '系统', icon: 'pulse' },
      { path: '/nasdeck/temps', title: '温度', icon: 'temp' },
      { path: '/nasdeck/sys-hist', title: '趋势', icon: 'hist' },
    ],
  },
  {
    items: [
      { path: '/nasdeck/docker', title: 'Docker', icon: 'docker', badge: 4 },
      { path: '/nasdeck/ports', title: '端口', icon: 'net' },
      { path: '/nasdeck/fan', title: '风扇', icon: 'fan' },
    ],
  },
  {
    items: [
      { path: '/nasdeck/automation', title: '自动化', icon: 'shield', badge: 2, badgeHot: true },
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

/** 存储卷页 */
export const storage = {
  array: {
    name: 'md126',
    level: 'RAID 6',
    totalText: '总容量 21.8 TB',
    membersText: '成员 4 盘 + 0 热备',
    activityText: '无重建 / 校验活动',
    running: true,
  },
  devices: [
    {
      name: 'sda',
      model: 'WDC WD40EFRX',
      slot: 1,
      fs: 'RAID 成员',
      tempC: 34,
      readText: '↓ 1.2 MB/s',
      writeText: '↑ 0.3 MB/s',
      meterPercent: 100,
      meterClass: 'c-ok',
      capacityText: '4 TB · 100% 成员',
      status: '正常',
    },
    {
      name: 'sdb',
      model: 'WDC WD40EFRX',
      slot: 2,
      fs: 'RAID 成员',
      tempC: 35,
      readText: '↓ 0.8 MB/s',
      writeText: '↑ 0.2 MB/s',
      meterPercent: 100,
      meterClass: 'c-ok',
      capacityText: '4 TB · 100% 成员',
      status: '正常',
    },
    {
      name: 'sdc',
      model: 'Seagate ST8000VN0022',
      slot: 3,
      fs: 'RAID 成员',
      tempC: 47,
      readText: '↓ 4.1 MB/s',
      writeText: '↑ 2.6 MB/s',
      meterPercent: 100,
      meterClass: 'c-warn',
      capacityText: '8 TB · SMART 05 警告',
      status: '警告 (05)',
    },
    {
      name: 'sdd',
      model: 'Seagate ST8000VN0022',
      slot: 4,
      fs: 'RAID 成员',
      tempC: 39,
      readText: '↓ 0.4 MB/s',
      writeText: '↑ 0.1 MB/s',
      meterPercent: 100,
      meterClass: 'c-ok',
      capacityText: '8 TB · 100% 成员',
      status: '正常',
    },
    {
      name: 'nvme0n1',
      model: 'Samsung PM883',
      slot: 5,
      fs: 'Btrfs · 缓存',
      tempC: 41,
      readText: '↓ 12.0 MB/s',
      writeText: '↑ 6.4 MB/s',
      meterPercent: 64,
      meterClass: 'c-info',
      capacityText: '308 / 480 GB · 64%',
      status: '正常',
    },
  ],
  volume: {
    name: 'vol1',
    usedText: '8.2 / 10.9 TB',
    percent: 75,
    fs: 'Btrfs',
    mount: '/vol1',
  },
  cloud: {
    name: 'backup',
    type: '阿里云 OSS',
    usage: '异地备份',
    lastSync: '今日 04:00',
    usedText: '6.4 / 20 TB',
  },
};

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

/** Docker 页 */
export const docker = {
  containers: [
    {
      name: 'plex',
      av: 'P',
      avClass: 'c4',
      running: true,
      mem: '1.2 GB',
      cpu: '3.4%',
      net: '↓2.1 ↑0.4 MB/s',
      ports: '32400→32400',
      up: '6 天',
    },
    {
      name: 'qBittorrent',
      av: 'q',
      avClass: 'c1',
      running: true,
      mem: '420 MB',
      cpu: '1.1%',
      net: '↓8.9 ↑1.2 MB/s',
      ports: '6881→6881',
      up: '2 天',
    },
    {
      name: 'homeassistant',
      av: 'h',
      avClass: 'c3',
      running: true,
      mem: '660 MB',
      cpu: '0.8%',
      net: '↓0.1 ↑0.1 MB/s',
      ports: '8123→8123',
      up: '23 天',
    },
    { name: 'memcached', av: 'm', avClass: 'c2', running: false },
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
    { name: 'CPU_FAN', rpm: 1220, duty: 46, pwm: true },
    { name: '前板_FAN', rpm: 980, duty: 38, pwm: false },
    { name: '后板_FAN', rpm: 1450, duty: 52, pwm: true },
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

/** 自动化页 */
export const automation = {
  alertRule: { metric: '温度', threshold: '60', duration: '60 s' },
  report: { schedule: '每日 08:00', formats: ['MD', 'HTML', 'CSV'] },
  logs: [
    { time: '10:21:04', level: 'warn', text: 'WARN  disk3 smart_attr 05 递增 (12 → 13)' },
    { time: '10:32:11', level: 'info', text: 'INFO  poll system ok (1s)' },
    { time: '10:32:10', level: 'warn', text: 'WARN  temp rear 61°C > 60°C' },
    { time: '10:30:00', level: 'info', text: 'INFO  report daily exported md/html' },
    { time: '09:58:41', level: 'bad', text: 'ERR   fan api timeout → 已重试成功' },
    { time: '09:41:02', level: 'info', text: 'INFO  detect refresh ok (smartctl × 6)' },
    { time: '09:40:11', level: 'info', text: 'INFO  fan takeover on → policy: curve1' },
    { time: '08:22:47', level: 'bad', text: 'ERR   storcli timeout (bbu query) → skip' },
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
