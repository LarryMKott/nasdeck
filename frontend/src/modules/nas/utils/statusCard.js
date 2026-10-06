'use strict';

/**
 * 状态分享卡片（脑洞 B）：总览数据 → 品牌橙渐变 PNG，一键下载发群晒 NAS。
 * Canvas 2D 手绘无依赖；数据全部来自总览页已就绪的 dashboard 形状，缺失项画"—"。
 */

/** 字节工具：canvas 内无 CSS 变量，色值与 UNRAID 橙主题对齐 */
const C = {
  bg0: '#1a1008',
  bg1: '#2a160a',
  card: 'rgba(255,255,255,0.045)',
  line: 'rgba(241,90,44,0.35)',
  text: '#f0f0f2',
  sub: '#8b8d95',
  acc: '#f15a2c',
  accHi: '#ff6e3f',
  ok: '#3fb68b',
  warn: '#eca43c',
  bad: '#e5484d',
};

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function bigStat(ctx, x, y, w, label, value, unit, color = C.text) {
  ctx.fillStyle = C.card;
  roundRect(ctx, x, y, w, 118, 14);
  ctx.fill();
  ctx.fillStyle = C.sub;
  ctx.font = '600 15px Inter, "Microsoft YaHei", sans-serif';
  ctx.fillText(label, x + 20, y + 32);
  ctx.fillStyle = color;
  ctx.font = '700 46px Inter, "Segoe UI", sans-serif';
  ctx.fillText(value, x + 18, y + 88);
  const vw = ctx.measureText(value).width;
  ctx.fillStyle = C.sub;
  ctx.font = '400 17px Inter, sans-serif';
  ctx.fillText(unit, x + 24 + vw, y + 88);
}

/**
 * 绘制并下载状态卡 PNG。
 *
 * @param {object} dash 总览页 dashboard 形状（cpu/mem/array/system/gpu/net/disks）
 * @param {object} [extras] 可选补充 { diskTemps: [{label, celsius}], diskHealth: {...} }
 * @returns {string} 下载文件名
 */
export function downloadStatusCard(dash, extras = {}) {
  const W = 1080;
  const H = 620;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');

  // 背景：纵向品牌橙渐变 + 右上光晕
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, C.bg1);
  grad.addColorStop(1, C.bg0);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, W, H);
  const glow = ctx.createRadialGradient(W * 0.85, -80, 40, W * 0.85, -80, 520);
  glow.addColorStop(0, 'rgba(241,90,44,0.28)');
  glow.addColorStop(1, 'rgba(241,90,44,0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, 320);

  // 头部：logo + 标题
  ctx.fillStyle = C.acc;
  roundRect(ctx, 44, 40, 40, 40, 11);
  ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.fillRect(54, 50, 20, 9);
  ctx.fillRect(54, 62, 13, 9);
  ctx.font = '800 30px Inter, "Segoe UI", sans-serif';
  ctx.fillText('nasdeck', 98, 70);
  ctx.fillStyle = C.sub;
  ctx.font = '400 17px Inter, sans-serif';
  ctx.fillText('NAS 硬件监控 · 状态速览', 98, 96);
  ctx.textAlign = 'right';
  ctx.fillText(new Date().toLocaleString('zh-CN', { hour12: false }), W - 44, 70);
  ctx.textAlign = 'left';
  ctx.strokeStyle = C.line;
  ctx.beginPath();
  ctx.moveTo(44, 118);
  ctx.lineTo(W - 44, 118);
  ctx.stroke();

  // 四大指标
  const bw = (W - 88 - 3 * 18) / 4;
  bigStat(
    ctx,
    44,
    142,
    bw,
    'CPU',
    dash.cpu?.percent != null ? String(dash.cpu.percent) : '—',
    '%',
    C.accHi
  );
  bigStat(
    ctx,
    44 + bw + 18,
    142,
    bw,
    '内存',
    dash.mem?.percent != null ? String(dash.mem.percent) : '—',
    '%'
  );
  bigStat(
    ctx,
    44 + 2 * (bw + 18),
    142,
    bw,
    '网速 ↓',
    dash.net?.rxValue != null ? String(dash.net.rxValue) : '—',
    dash.net?.rxUnit || ''
  );
  const gpuPct = dash.gpu?.percent;
  bigStat(
    ctx,
    44 + 3 * (bw + 18),
    142,
    bw,
    'GPU',
    gpuPct != null && gpuPct !== 0 ? String(gpuPct) : dash.gpu?.percent === 0 ? '0' : '—',
    '%'
  );

  // 阵列 / 运行 / 系统 三行信息卡
  ctx.fillStyle = C.card;
  roundRect(ctx, 44, 284, W - 88, 128, 14);
  ctx.fill();
  const info = [
    ['阵列', `${dash.array?.usedText ?? '—'}${dash.array?.level ? ` · ${dash.array.level}` : ''}`],
    ['运行时长', dash.system?.uptime ?? '—'],
    ['系统', dash.system?.osVersion ?? '—'],
    ['负 载', dash.system?.loadText ?? '—'],
  ];
  info.forEach(([label, value], i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    ctx.fillStyle = C.sub;
    ctx.font = '600 15px Inter, "Microsoft YaHei", sans-serif';
    ctx.fillText(label, 68 + col * ((W - 88) / 2), 322 + row * 48);
    ctx.fillStyle = C.text;
    ctx.font = '600 19px Inter, "Microsoft YaHei", sans-serif';
    ctx.fillText(String(value ?? '—'), 170 + col * ((W - 88) / 2), 323 + row * 48);
  });

  // 硬盘温度条（有数据才画）
  const temps = (extras.diskTemps || []).slice(0, 8);
  if (temps.length) {
    ctx.fillStyle = C.sub;
    ctx.font = '600 15px Inter, "Microsoft YaHei", sans-serif';
    ctx.fillText('硬盘温度', 44, 452);
    const bw2 = (W - 88 - (temps.length - 1) * 14) / temps.length;
    temps.forEach((t, i) => {
      const x = 44 + i * (bw2 + 14);
      ctx.fillStyle = C.card;
      roundRect(ctx, x, 466, bw2, 56, 10);
      ctx.fill();
      const c = t.celsius >= 50 ? C.bad : t.celsius >= 45 ? C.warn : C.ok;
      ctx.fillStyle = c;
      ctx.font = '700 24px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(`${Math.round(t.celsius)}°`, x + bw2 / 2, 496);
      ctx.fillStyle = C.sub;
      ctx.font = '400 13px Inter, sans-serif';
      ctx.fillText(t.label || `盘${i + 1}`, x + bw2 / 2, 514);
      ctx.textAlign = 'left';
    });
  }

  // 底部：告警状态 + 生成时间
  const firing = extras.firingCount ?? 0;
  ctx.fillStyle = firing ? C.warn : C.ok;
  ctx.font = '600 16px Inter, "Microsoft YaHei", sans-serif';
  ctx.fillText(firing ? `● ${firing} 条告警进行中` : '● 全部平静', 44, H - 40);
  ctx.fillStyle = C.sub;
  ctx.textAlign = 'right';
  ctx.fillText('by nasdeck · fnOS 硬件监控', W - 44, H - 40);
  ctx.textAlign = 'left';

  // 下载
  const name = `nasdeck-status-${new Date().toISOString().slice(0, 10)}.png`;
  canvas.toBlob((blob) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  });
  return name;
}
