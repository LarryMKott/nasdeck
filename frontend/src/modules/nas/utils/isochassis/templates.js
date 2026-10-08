'use strict';

/**
 * 传感器自动映射 + 参数化模板（花活三期 R1）：inventory × template → layout JSON。
 * 「模型即数据」是机型自适应的前提——渲染器固定不变，适配全部发生在生成层。
 * 全部纯函数：同一 inventory 恒定输出同一 layout（可单测）。
 */

/**
 * 传感器自动映射：zone 归类优先（后端 cpu/nvme/disk/board 分区已就绪），
 * 命名启发式兜底（cpu/pkg/core/tctl → CPU；acpitz/pch/system → 环境）；
 * 其余为「游离传感器」吸附主板区。盘温不走此映射（按 device 序 → 盘位）。
 * @param {Array<{key: string, label: string, zone?: string, chip?: string, celsius: number, grade?: string}>} sensors
 * @returns {{cpu: object|null, nvme: object[], board: object|null, other: object[]}}
 */
export function mapSensors(sensors = [], remap = {}) {
  const text = (s) => `${s.key ?? ''} ${s.label ?? ''} ${s.chip ?? ''}`.toLowerCase();
  const nameHit = (s, ...words) => words.some((w) => text(s).includes(w));
  const out = { cpu: null, nvme: [], board: null, other: [] };
  for (const s of sensors) {
    const zone = s.zone ?? '';
    if (
      out.cpu === null &&
      (zone === 'cpu' || nameHit(s, 'cpu', 'package', 'core', 'tctl', 'tdie'))
    ) {
      out.cpu = s;
    } else if (zone === 'nvme' || text(s).includes('nvme')) {
      out.nvme.push(s);
    } else if (zone === 'board' || nameHit(s, 'acpitz', 'pch', 'system', 'board')) {
      out.board ??= s;
    } else if (zone !== 'disk') {
      out.other.push(s);
    }
  }
  // R3 持久化重映射覆盖：{ sensorKey: 'cpu'|'nvme'|'board'|'free' }——用户修正自动映射
  for (const [key, role] of Object.entries(remap || {})) {
    if (!['cpu', 'nvme', 'board', 'free'].includes(role)) continue;
    const s = sensors.find((x) => x.key === key);
    if (!s) continue;
    if (out.cpu === s) out.cpu = null;
    out.nvme = out.nvme.filter((x) => x !== s);
    if (out.board === s) out.board = null;
    out.other = out.other.filter((x) => x !== s);
    if (role === 'cpu') out.cpu = s;
    else if (role === 'nvme') out.nvme.push(s);
    else if (role === 'board') out.board = s;
    else out.other.push(s);
  }
  return out;
}

/**
 * 温度 → 面色等级（沿用后端 60/75 分级；null 中性）。
 * @param {number|null} celsius
 * @returns {''|'warm'|'hot'|'neutral'}
 */
export function tempGrade(celsius) {
  if (celsius == null) return 'neutral';
  if (celsius >= 75) return 'hot';
  if (celsius >= 60) return 'warm';
  return '';
}

/**
 * tower 塔式侧透模板（默认）：盘笼行数 = ⌈盘数/5⌉；风扇位 = fan_outputs 实数；
 * 内存条按 detect 槽位（缺省示意 2 根）；GPU/网口按清单增删。
 * 造型允许示意，数据只经颜色/动画/数字承载（花活三期约定）。
 * @param {object} inv inventory：{sensors, fans, disks, board, gpuAvailable}
 * @returns {{kind: 'tower', size: {w,d,h}, boxes: object[]}}
 */
export function towerTemplate(inv, remap = {}) {
  // 投影语义：+x 屏幕右下、+y 屏幕左下、+z 上——(0,0) 远角朝上，开放角 (W, D) 朝观察者。
  // 机壳两墙贴远侧平面（x=0 / y=0），永不会被画家序（x+y 升序）画到部件之前。
  const W = 15;
  const D = 19;
  const H = 11;
  const boxes = [];
  const add = (b) => {
    boxes.push(b);
    return b;
  };

  // 机壳：底板 + 左墙（x=0）+ 右墙（y=0）
  add({ id: 'case-floor', kind: 'case', x: 0, y: 0, z: 0, w: W, d: D, h: 0.5, label: '' });
  add({ id: 'case-wall-l', kind: 'case', x: 0, y: 0, z: 0, w: 0.5, d: D, h: H, label: '' });
  add({ id: 'case-wall-r', kind: 'case', x: 0, y: 0, z: 0, w: W, d: 0.5, h: H, label: '' });

  const m = mapSensors(inv.sensors, remap);

  // 主板基板：远半区（贴 y=0 右墙）
  add({ id: 'mobo', kind: 'mobo', x: 5, y: 0.6, z: 0.5, w: 6.8, d: 8.6, h: 0.4 });

  // CPU 散热器顶盖：面色 = cpu 温度分级，悬停实时读数
  const cpu = m.cpu;
  add({
    id: 'cpu',
    kind: 'cpu',
    x: 5.6,
    y: 1.2,
    z: 0.9,
    w: 3.2,
    d: 3.2,
    h: 2.4,
    label: 'CPU',
    bind: cpu
      ? { type: 'temp', key: cpu.key, celsius: cpu.celsius }
      : { type: 'temp', key: null, celsius: null },
  });

  // 内存条：根数按 detect 槽位（缺省示意 2 根）；贴 y=0 墙竖插
  const dimmN = Math.max(2, Math.min(4, inv.dimms || 2));
  for (let i = 0; i < dimmN; i += 1) {
    add({
      id: `ram${i}`,
      kind: 'ram',
      x: 9.4 + i * 0.85,
      y: 1.2,
      z: 0.9,
      w: 0.55,
      d: 5.4,
      h: 2.1,
      label: `DIMM${i + 1}`,
    });
  }

  // M.2 区：nvme 传感器存在才渲染（无源部件自动隐去）
  if (m.nvme.length) {
    add({
      id: 'm2',
      kind: 'm2',
      x: 5.6,
      y: 5,
      z: 0.9,
      w: 3.4,
      d: 1.7,
      h: 0.5,
      label: 'M.2',
      bind: { type: 'temp', key: m.nvme[0].key, celsius: m.nvme[0].celsius },
    });
  }

  // 显卡（可选部件）：GPU 实时分量可用才渲染（无卡整件不渲染）；CPU/内存前方悬置
  if (inv.gpuAvailable) {
    add({
      id: 'gpu',
      kind: 'gpu',
      x: 5.3,
      y: 4.6,
      z: 3.5,
      w: 8.2,
      d: 2.6,
      h: 2.2,
      label: 'GPU',
      bind: { type: 'gpu' },
    });
  }

  // 盘笼：近半区（大 y），每行 5 盘位，行数 = ⌈盘数/5⌉；盘温按 device 序 → 盘位 1..N
  const disks = inv.disks ?? [];
  disks.slice(0, 15).forEach((disk, i) => {
    const col = i % 5;
    const row = Math.floor(i / 5);
    add({
      id: `bay${i}`,
      kind: 'bay',
      x: 0.8 + col * 2.75,
      y: D - 3.6 - row * 3.1,
      z: 0.5,
      w: 2.5,
      d: 2.8,
      h: 1.9,
      label: disk.device || `#${i + 1}`,
      bind: { type: 'bay', device: disk.device, celsius: disk.tempC, iops: null },
      tooltip: [disk.model, disk.capacity].filter(Boolean).join(' · '),
    });
  });
  if (!disks.length) {
    add({
      id: 'bay-none',
      kind: 'case',
      x: 0.8,
      y: D - 4,
      z: 0.5,
      w: 13.4,
      d: 2.8,
      h: 0.3,
      label: '',
    });
  }

  // 电源：远左角底置，悬浮牌 = RAPL 功耗（无 RAPL 显"—"）
  add({
    id: 'psu',
    kind: 'psu',
    x: 0.7,
    y: 0.7,
    z: 0.5,
    w: 4.6,
    d: 3.8,
    h: 2.6,
    label: 'PSU',
    bind: { type: 'power' },
  });

  // 风扇：y=0 右墙顶部横列，位 = fan_outputs 实数（R2 扇叶转动）
  const fans = (inv.fans ?? []).slice(0, 3);
  fans.forEach((fan, i) => {
    add({
      id: `fan${i}`,
      kind: 'fan',
      x: 1.2 + i * 4.4,
      y: 0.55,
      z: H - 3.4,
      w: 3.6,
      d: 0.7,
      h: 3,
      label: fan.name || `FAN${i + 1}`,
      bind: { type: 'fan', rpm: fan.rpm ?? 0 },
    });
  });

  // 网口：x=0 左墙下段（R2 按吞吐闪烁）
  const nics = Math.min(4, inv.nics ?? 1);
  for (let i = 0; i < nics; i += 1) {
    add({
      id: `net${i}`,
      kind: 'net',
      x: 0.55,
      y: D - 2.2 - i * 1.2,
      z: 0.8,
      w: 0.75,
      d: 0.9,
      h: 0.8,
      label: '',
      bind: { type: 'net', index: i },
    });
  }

  // 游离传感器：小方块吸附主板前缘，悬停可读数（有数据就不丢）
  (m.other ?? []).slice(0, 4).forEach((s, i) => {
    add({
      id: `free${i}`,
      kind: 'free',
      x: 5.2 + i * 1.1,
      y: 9.4,
      z: 0.9,
      w: 0.9,
      d: 0.9,
      h: 0.7,
      label: s.label || s.key,
      bind: { type: 'temp', key: s.key, celsius: s.celsius },
    });
  });

  return { kind: 'tower', size: { w: W, d: D, h: H }, boxes };
}

export function virtualTemplate(inv, remap = {}) {
  const W = 16;
  const D = 13;
  const H = 4.5; // 场景内无高件：压低包围盒避免 viewBox 竖向留白
  const boxes = [];
  const add = (b) => boxes.push(b);

  add({ id: 'slab', kind: 'mobo', x: 0, y: 0, z: 0, w: W, d: D, h: 0.4, label: '' });

  const m = mapSensors(inv.sensors, remap);
  const cpu = m.cpu;
  add({
    id: 'cpu',
    kind: 'cpu',
    x: 1.4,
    y: 4.2,
    z: 0.4,
    w: 4,
    d: 4,
    h: 1.4,
    label: 'vCPU',
    bind: cpu
      ? { type: 'temp', key: cpu.key, celsius: cpu.celsius }
      : { type: 'temp', key: null, celsius: null },
  });

  const dimmN = Math.max(2, Math.min(4, inv.dimms || 2));
  for (let i = 0; i < dimmN; i += 1) {
    add({
      id: `ram${i}`,
      kind: 'ram',
      x: 6.2 + i * 0.9,
      y: 4.4,
      z: 0.4,
      w: 0.6,
      d: 4.4,
      h: 1.3,
      label: `DIMM${i + 1}`,
    });
  }

  // 盘列：右半区图标化薄板
  (inv.disks ?? []).slice(0, 8).forEach((disk, i) => {
    add({
      id: `vdisk${i}`,
      kind: 'bay',
      x: 9.2 + (i % 2) * 3.2,
      y: 0.8 + Math.floor(i / 2) * 2.9,
      z: 0.4,
      w: 2.8,
      d: 2.5,
      h: 1.2,
      label: disk.device || `#${i + 1}`,
      bind: { type: 'bay', device: disk.device, celsius: disk.tempC },
      tooltip: [disk.model, disk.capacity].filter(Boolean).join(' · '),
    });
  });

  // 网卡芯片列
  const nics = Math.min(4, inv.nics ?? 1);
  for (let i = 0; i < nics; i += 1) {
    add({
      id: `net${i}`,
      kind: 'net',
      x: 1.6 + i * 1.8,
      y: 0.8,
      z: 0.4,
      w: 1.3,
      d: 1.1,
      h: 0.9,
      label: '',
      bind: { type: 'net', index: i },
    });
  }

  (m.other ?? []).slice(0, 3).forEach((s, i) => {
    add({
      id: `free${i}`,
      kind: 'free',
      x: 6.4 + i * 1.2,
      y: 10.6,
      z: 0.4,
      w: 1,
      d: 1,
      h: 0.8,
      label: s.label || s.key,
      bind: { type: 'temp', key: s.key, celsius: s.celsius },
    });
  });

  return { kind: 'virtual', size: { w: W, d: D, h: H }, boxes };
}

/** 机架式模板（1U/2U/4U）：前置横排盘位（8/12 盘多列）、风扇横列、后置长条电源。 */
export function rackTemplate(inv, remap = {}) {
  const W = 22;
  const D = 11;
  const H = 6;
  const boxes = [];
  const add = (b) => boxes.push(b);

  add({ id: 'case-floor', kind: 'case', x: 0, y: 0, z: 0, w: W, d: D, h: 0.4 });
  add({ id: 'case-wall-l', kind: 'case', x: 0, y: 0, z: 0, w: 0.4, d: D, h: H });
  add({ id: 'case-wall-r', kind: 'case', x: 0, y: 0, z: 0, w: W, d: 0.4, h: H });

  const m = mapSensors(inv.sensors, remap);
  const cpu = m.cpu;
  add({ id: 'mobo', kind: 'mobo', x: 7.4, y: 0.5, z: 0.4, w: 9, d: 9.6, h: 0.35 });
  add({
    id: 'cpu',
    kind: 'cpu',
    x: 8.2,
    y: 1.1,
    z: 0.75,
    w: 3,
    d: 3,
    h: 1.4,
    label: 'CPU',
    bind: cpu
      ? { type: 'temp', key: cpu.key, celsius: cpu.celsius }
      : { type: 'temp', key: null, celsius: null },
  });
  const dimmN = Math.max(2, Math.min(6, inv.dimms || 2));
  for (let i = 0; i < dimmN; i += 1) {
    add({
      id: `ram${i}`,
      kind: 'ram',
      x: 12 + (i % 3) * 0.85,
      y: 1.1 + Math.floor(i / 3) * 3.2,
      z: 0.75,
      w: 0.55,
      d: 2.8,
      h: 1.2,
      label: `DIMM${i + 1}`,
    });
  }
  if (m.nvme.length) {
    add({
      id: 'm2',
      kind: 'm2',
      x: 8.2,
      y: 5,
      z: 0.75,
      w: 4.4,
      d: 1.5,
      h: 0.4,
      label: 'M.2',
      bind: { type: 'temp', key: m.nvme[0].key, celsius: m.nvme[0].celsius },
    });
  }

  // 前置横排盘位：近半区（大 y），单/双行
  const disks = inv.disks ?? [];
  disks.slice(0, 12).forEach((disk, i) => {
    add({
      id: `bay${i}`,
      kind: 'bay',
      x: 0.6 + (i % 6) * 1.5,
      y: D - 2.6 - Math.floor(i / 6) * 2.4,
      z: 0.4,
      w: 1.3,
      d: 2.1,
      h: 1.5,
      label: disk.device || `#${i + 1}`,
      bind: { type: 'bay', device: disk.device, celsius: disk.tempC, iops: null },
      tooltip: [disk.model, disk.capacity].filter(Boolean).join(' · '),
    });
  });

  add({
    id: 'psu',
    kind: 'psu',
    x: 0.6,
    y: 0.5,
    z: 0.4,
    w: 6.2,
    d: 3.2,
    h: 1.6,
    label: 'PSU',
    bind: { type: 'power' },
  });
  const fans = (inv.fans ?? []).slice(0, 3);
  fans.forEach((fan, i) => {
    add({
      id: `fan${i}`,
      kind: 'fan',
      x: 7.6 + i * 2.9,
      y: 0.45,
      z: H - 2.4,
      w: 2.4,
      d: 0.5,
      h: 1.9,
      label: fan.name || `FAN${i + 1}`,
      bind: { type: 'fan', rpm: fan.rpm ?? 0 },
    });
  });
  const nics = Math.min(4, inv.nics ?? 1);
  for (let i = 0; i < nics; i += 1) {
    add({
      id: `net${i}`,
      kind: 'net',
      x: 0.45,
      y: D - 1.6 - i * 1,
      z: H - 1.6,
      w: 0.7,
      d: 0.8,
      h: 0.7,
      label: '',
      bind: { type: 'net', index: i },
    });
  }
  (m.other ?? []).slice(0, 3).forEach((s, i) => {
    add({
      id: `free${i}`,
      kind: 'free',
      x: 7.6 + i * 1.1,
      y: 8.6,
      z: 0.75,
      w: 0.85,
      d: 0.85,
      h: 0.65,
      label: s.label || s.key,
      bind: { type: 'temp', key: s.key, celsius: s.celsius },
    });
  });
  return { kind: 'rack', size: { w: W, d: D, h: H }, boxes };
}

/** 紧凑型模板（NUC / ITX / 蜗牛星际）：单列盘位、低矮散热块、无 GPU 位、电源外置块。 */
export function compactTemplate(inv, remap = {}) {
  const W = 9;
  const D = 10;
  const H = 6.5;
  const boxes = [];
  const add = (b) => boxes.push(b);

  add({ id: 'case-floor', kind: 'case', x: 0, y: 0, z: 0, w: W, d: D, h: 0.4 });
  add({ id: 'case-wall-l', kind: 'case', x: 0, y: 0, z: 0, w: 0.4, d: D, h: H });
  add({ id: 'case-wall-r', kind: 'case', x: 0, y: 0, z: 0, w: W, d: 0.4, h: H });

  const m = mapSensors(inv.sensors, remap);
  const cpu = m.cpu;
  add({ id: 'mobo', kind: 'mobo', x: 0.6, y: 0.5, z: 0.4, w: 6.4, d: 8.8, h: 0.35 });
  add({
    id: 'cpu',
    kind: 'cpu',
    x: 0.9,
    y: 0.9,
    z: 0.75,
    w: 2.6,
    d: 2.6,
    h: 1, // 板载低矮散热块
    label: 'CPU',
    bind: cpu
      ? { type: 'temp', key: cpu.key, celsius: cpu.celsius }
      : { type: 'temp', key: null, celsius: null },
  });
  const dimmN = Math.max(1, Math.min(2, inv.dimms || 1));
  for (let i = 0; i < dimmN; i += 1) {
    add({
      id: `ram${i}`,
      kind: 'ram',
      x: 4.4 + i * 0.8,
      y: 0.9,
      z: 0.75,
      w: 0.6,
      d: 4.4,
      h: 1.2,
      label: `DIMM${i + 1}`,
    });
  }
  (inv.disks ?? []).slice(0, 5).forEach((disk, i) => {
    add({
      id: `bay${i}`,
      kind: 'bay',
      x: 0.8,
      y: D - 1.4 - i * 1.9,
      z: 0.4,
      w: 5.4,
      d: 1.6,
      h: 1.3,
      label: disk.device || `#${i + 1}`,
      bind: { type: 'bay', device: disk.device, celsius: disk.tempC, iops: null },
      tooltip: [disk.model, disk.capacity].filter(Boolean).join(' · '),
    });
  });
  add({
    id: 'psu',
    kind: 'psu',
    x: 0.5,
    y: 7.4,
    z: 0.4,
    w: 2.6,
    d: 2,
    h: 1.4,
    label: 'PSU',
    bind: { type: 'power' },
  });
  const fans = (inv.fans ?? []).slice(0, 1);
  fans.forEach((fan, i) => {
    add({
      id: `fan${i}`,
      kind: 'fan',
      x: 3.4 + i * 2.6,
      y: 0.45,
      z: H - 2.2,
      w: 2,
      d: 0.45,
      h: 1.7,
      label: fan.name || 'FAN',
      bind: { type: 'fan', rpm: fan.rpm ?? 0 },
    });
  });
  const nics = Math.min(2, inv.nics ?? 1);
  for (let i = 0; i < nics; i += 1) {
    add({
      id: `net${i}`,
      kind: 'net',
      x: 0.45,
      y: D - 1.2 - i * 1,
      z: H - 1.3,
      w: 0.6,
      d: 0.7,
      h: 0.6,
      label: '',
      bind: { type: 'net', index: i },
    });
  }
  return { kind: 'compact', size: { w: W, d: D, h: H }, boxes };
}

/**
 * 模板自动选择：DMI 厂商/型号命中虚拟化特征 → virtual；其余默认 tower。
 * 读不到 DMI（board 缺失）按 tower（切错只影响观感不影响数据）。
 * @param {object} inv inventory（含 board: {vendor, model, product_name}）
 * @returns {{kind: 'tower'|'virtual', size: object, boxes: object[]}}
 */
export function buildLayout(inv, forced = 'auto') {
  const map = {
    tower: towerTemplate,
    rack: rackTemplate,
    compact: compactTemplate,
    virtual: virtualTemplate,
  };
  if (forced && forced !== 'auto' && map[forced]) return map[forced](inv);
  const txt = [inv.board?.vendor, inv.board?.model, inv.board?.product_name]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  const isVm = [
    'qemu',
    'kvm',
    'vmware',
    'microsoft corporation',
    'virtualbox',
    'bochs',
    'xen',
  ].some((w) => txt.includes(w));
  return isVm ? virtualTemplate(inv) : towerTemplate(inv);
}
