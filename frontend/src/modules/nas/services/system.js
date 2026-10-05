'use strict';

/**
 * 系统视图适配层：Docker / 端口 / 关于 / 硬件检测。
 */

import * as mock from '../mock';
import { getDocker, getEnv, getPorts, getSystemInfo } from '../api/endpoints/system';
import { getHardware } from '../api/endpoints/hardware';
import { getDisks } from '../api/endpoints/storage';
import { pick, uptimeText } from './shared';

/** Docker 页取数：不可用原因经 extra 透出（useViewData extra）
 * @returns {Promise<{data: object, live: boolean, extra: string|null}>} */
export async function fetchDocker() {
  const resp = await getDocker().catch(() => null);
  if (resp === null) return { data: mock.docker, live: false, extra: null }; // 后端不可达才演示
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
    extra: resp.available ? null : (resp.reason ?? 'docker 不可用'),
  };
}

/** 端口页取数：只展示 LISTEN 前 20 条，行内附搜索/确认文案
 * @returns {Promise<{data: {list: Array}, live: boolean}>} */
export async function fetchPorts() {
  const entries = await getPorts().catch(() => null);
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

/** 关于页取数：版本 + 构建信息
 * @returns {Promise<{data: object, live: boolean}>} */
export async function fetchAbout() {
  const info = await getSystemInfo().catch(() => null);
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
    env: {
      runtime: [],
      schemes: [],
      tools: [],
      drivers: [],
      storcli: { ok: false, path: '', desc: '' },
    },
  };
}

/** 硬件检测页取数（§3.7 /hardware 只读 + 环境自检 + 盘位）
 * @returns {Promise<{data: ReturnType<emptyDetect>, live: boolean}>} */
export async function fetchDetect() {
  const [hwS, infoS, disksS, envS] = await Promise.allSettled([
    getHardware(),
    getSystemInfo(),
    getDisks(),
    getEnv(),
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
