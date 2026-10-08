'use strict';

/**
 * 示波器渲染内核（花活二期 P 自 OscilloscopeView 抽出，示波器/大屏波形带共用）：
 * 通道自动量程（min 保底 1，避免零基线成直线）+ 荧光折线。纯函数不持状态。
 */

/**
 * 单通道荧光曲线。
 * @param {CanvasRenderingContext2D} ctx 画布上下文（调用方负责 dpr 与 clearRect）
 * @param {{t:number, v:Record<string, number|null>}[]} data 点缓冲（t 升序，毫秒）
 * @param {string} key 通道键（取 p.v[key]，null 跳过）
 * @param {string} color 通道色
 * @param {object} g 几何与窗口：{ w, h, t0, tNow, padBottom?, padTop?, lineWidth?, glow? }
 * @returns {{min:number, max:number}|null} 量程；窗口内有效点不足两个时 null（不画）
 */
export function drawGlowChannel(ctx, data, key, color, g) {
  const vals = [];
  for (const p of data) {
    if (p.t < g.t0) continue;
    const v = p.v[key];
    if (v != null) vals.push(v);
  }
  if (vals.length < 2) return null;
  const max = Math.max(...vals, 1);
  const min = Math.min(...vals, 0);
  const span = max - min || 1;
  const winMs = g.tNow - g.t0;
  const padB = g.padBottom ?? 6;
  const padT = g.padTop ?? 18;
  ctx.strokeStyle = color;
  ctx.lineWidth = g.lineWidth ?? 1.6;
  ctx.shadowColor = color;
  ctx.shadowBlur = g.glow ?? 6; // 荧光辉光
  ctx.beginPath();
  let started = false;
  for (const p of data) {
    if (p.t < g.t0 || p.v[key] == null) continue;
    const x = ((p.t - g.t0) / winMs) * g.w;
    const y = g.h - padB - ((p.v[key] - min) / span) * (g.h - padB - padT);
    started ? ctx.lineTo(x, y) : (ctx.moveTo(x, y), (started = true));
  }
  ctx.stroke();
  ctx.shadowBlur = 0;
  return { min, max };
}
