'use strict';

/**
 * 存储视图适配层：存储页（阵列/设备/卷/拓扑）与硬盘 SMART 页。
 */

import * as mock from '../mock';
import {
  getDisks,
  getRaid,
  getSelfTests,
  getSmartTrend,
  getVolumes,
} from '../api/endpoints/storage';
import { pick } from './shared';

/** live 形态骨架：无阵列/无盘/无卷时段保持空值，由模板空态兜底（不残留演示阵列） */
export function emptyStorage() {
  return {
    array: null,
    devices: [],
    volume: null,
    dataVolume: null,
    arrayController: null,
    topology: { controller: null, arrays: [], standalone: [] },
  };
}

/** 字节数 → TB 文本（拓扑/容量展示统一口径） */
function tbText(bytes) {
  return `${Math.round((bytes / 1024 ** 4) * 10) / 10} TB`;
}

/** md 成员分区名 → 父盘名（sda2→sda；nvme0n1p2→nvme0n1） */
function diskOfPartition(dev) {
  return (dev || '').replace(/p?\d+$/, '');
}

/** 存储页取数：raid/disks/volumes 三源并发，全不可达才整页演示回退
 * @returns {Promise<{data: ReturnType<emptyStorage>, live: boolean}>} */
export async function fetchStorage() {
  const [raidS, disksS, volsS] = await Promise.allSettled([getRaid(), getDisks(), getVolumes()]);
  const raid = pick(raidS);
  const disks = pick(disksS);
  const vols = pick(volsS);
  // 三源全不可达才整页演示回退；个别源缺失保持骨架空值
  if (!raid && !disks && !vols) return { data: mock.storage, live: false };

  const d = emptyStorage();
  const allVols = [...(raid?.hardware_raid ?? []), ...(raid?.software_raid ?? [])];
  const drives = raid?.drives ?? [];
  // 成员归属（拓扑 + 设备表角色共用）：storcli PD 按 sn 认领；md 成员分区按父盘认领。
  // VD 块设备与 PD 无可靠 join（契约 §2.8），按直连形态展示
  const memberSns = new Set(drives.filter((x) => x.sn).map((x) => x.sn));
  const hotspareSns = new Set(drives.filter((x) => x.hotspare && x.sn).map((x) => x.sn));
  const claimedDevices = new Set(
    (raid?.software_raid ?? []).flatMap((v) =>
      (v.members ?? []).map((m) => diskOfPartition(m.device))
    )
  );
  const volByMount = new Map((vols ?? []).map((v) => [v.mount, v]));
  const volByDevice = new Map(
    (vols ?? []).map((v) => [String(v.device || '').replace('/dev/', ''), v])
  );
  // md 成员是分区（sda2），容量从所属盘的分区清单取
  const partSizes = new Map();
  for (const disk of disks ?? []) {
    for (const p of disk.partitions ?? []) {
      if (p.size_bytes != null) partSizes.set(p.name, tbText(p.size_bytes));
    }
  }
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
    d.devices = disks.map((disk) => {
      const isHot = disk.serial && hotspareSns.has(disk.serial);
      const isMember =
        (disk.serial && memberSns.has(disk.serial)) || claimedDevices.has(disk.device);
      const fsPart = (disk.partitions ?? []).find((p) => p.fstype);
      const usagePart = (disk.partitions ?? []).find(
        (p) => p.mountpoint && volByMount.has(p.mountpoint)
      );
      const usage = usagePart ? volByMount.get(usagePart.mountpoint) : null;
      const usagePercent = usage ? Math.round(usage.percent) : null;
      return {
        name: disk.device,
        model: disk.model || disk.device,
        slot: null, // 无真实槽位数据源（storcli PD 不经 lsblk）：显式 '—'，不虚构盘位序号
        role: isHot ? '热备' : isMember ? 'RAID 成员' : null,
        alias: disk.alias || null,
        fsText: fsPart ? fsPart.fstype.toUpperCase() : null,
        tempC: disk.temp_c != null ? Math.round(disk.temp_c) : null,
        readText: '—',
        writeText: '—',
        usagePercent, // 仅挂载卷可计算真实用量；RAID 成员盘无独立用量，不显示 meter
        usageClass:
          usagePercent == null
            ? null
            : usagePercent >= 90
              ? 'c-bad'
              : usagePercent >= 75
                ? 'c-warn'
                : 'c-ok',
        capacityText: `${disk.size_human}${disk.serial ? ` · SN ${String(disk.serial).slice(-4)}` : ''}`,
        status:
          { passed: '正常', warning: '警告', failing: '故障', unknown: '未知' }[disk.health] ??
          '未知',
      };
    });
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

  // ---- 存储拓扑（真实层级：控制器→阵列→成员→分区/挂载点；契约 §2.5/§2.8 v2.3.5）----
  d.topology.arrays = allVols.map((vol) => {
    const mounted = volByDevice.get(vol.name) || volByDevice.get(vol.volume_id) || null;
    return {
      key: vol.volume_id || vol.name,
      name: vol.name,
      levelText: `RAID ${vol.level}`.replace('RAID unknown', 'RAID'),
      sizeText: vol.size_bytes ? tbText(vol.size_bytes) : null,
      state: vol.state || null,
      healthy: !!vol.healthy,
      source: vol.source,
      members: (vol.members ?? []).map((m) => ({
        label: m.slot || m.device || '成员',
        model: m.model || null,
        sizeText: m.size_human || (m.device ? partSizes.get(m.device) || null : null),
        state: m.state || null,
        hotspare: m.hotspare || (m.spare ? 'spare' : null),
        failed: !!(m.failed || m.faulty),
      })),
      volume: mounted
        ? {
            mount: mounted.mount,
            fs: mounted.fs_type,
            usedText: `${tbText(mounted.used_bytes)} / ${tbText(mounted.total_bytes)}`,
            percent: mounted.percent,
          }
        : null, // storcli VD 块设备与 PD 无可靠 join：卷信息经直连盘分区挂载点呈现
    };
  });
  d.topology.standalone = (disks ?? [])
    .filter(
      (disk) => !(disk.serial && memberSns.has(disk.serial)) && !claimedDevices.has(disk.device)
    )
    .map((disk) => ({
      name: disk.device,
      model: disk.model || null,
      sizeText: disk.size_human || null,
      alias: disk.alias || null,
      health: disk.health || 'unknown',
      tempC: disk.temp_c != null ? Math.round(disk.temp_c) : null,
      partitions: (disk.partitions ?? []).map((p) => ({
        name: p.name,
        fstype: p.fstype || null,
        sizeText: p.size_bytes != null ? tbText(p.size_bytes) : null,
        mountpoint: p.mountpoint || null,
      })),
    }));
  d.topology.controller = d.arrayController
    ? { mode: d.arrayController.mode, model: d.arrayController.model }
    : d.topology.arrays.length
      ? { mode: 'soft', model: null }
      : null;
  return { data: d, live: true };
}

/** 硬盘 SMART 页取数：磁盘清单 + 自检任务状态
 * @returns {Promise<{data: {list: Array, selftest: object|null}, live: boolean}>} */
export async function fetchDisks() {
  const [disksS, testsS] = await Promise.allSettled([getDisks(), getSelfTests()]);
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
      ? {
          device: running.device,
          label: `${running.device} · ${running.type}`,
          percent: running.percent ?? 0,
        }
      : null,
  };
  return { data: d, live: true };
}

/** 硬盘 SMART 趋势取数：live 取真实序列（smart_15m 采集），后端不可达回退演示序列
 * @param {string} device 不带 /dev/ 前缀
 * @param {string} metric 白名单见契约 §3.2
 * @param {number} [days] 窗口天数
 * @returns {Promise<{data: import('../../models/storage').SmartTrendResponse, live: boolean}>} */
export async function fetchDiskTrend(device, metric, days = 30) {
  try {
    return { data: await getSmartTrend(device, metric, days), live: true };
  } catch {
    return { data: mock.smartTrendDemo(device, metric, days), live: false };
  }
}
