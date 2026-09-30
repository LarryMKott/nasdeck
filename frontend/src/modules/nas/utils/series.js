'use strict';

/**
 * mock 时序数据工具（移植自 prototype/nasdeck-unraid.html 的随机序列生成）。
 * 种子随机保证同页面每次进入的曲线形态一致，观感接近真实历史。
 */

/** 补零（两位） */
function pad(n) {
  return (n < 10 ? '0' : '') + n;
}

/** 当前时刻 HH:mm:ss */
function nowHMS() {
  const d = new Date();
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/**
 * 创建种子伪随机数生成器（mulberry32）
 * @param {number} seed 种子
 * @returns {() => number} [0,1) 随机数
 */
function createRng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * 生成随机游走序列（带上下限回弹）
 * @param {number} n 点数
 * @param {number} seed 种子
 * @param {number} base 基准值
 * @param {number} vol 单步波动幅度
 * @param {number} min 下限
 * @param {number} max 上限
 * @returns {number[]}
 */
function walk(n, seed, base, vol, min, max) {
  const r = createRng(seed);
  let v = base;
  const out = [];
  for (let i = 0; i < n; i += 1) {
    v += (r() - 0.5) * vol;
    if (v < min) v = min + r() * (max - min) * 0.05;
    if (v > max) v = max - r() * (max - min) * 0.05;
    out.push(Math.round(v * 10) / 10);
  }
  return out;
}

/**
 * 生成最近 N 个采样点的时间标签
 * @param {number} count 点数
 * @param {number} stepSec 采样间隔（秒）
 * @param {boolean} [withDate] 是否带日期前缀
 * @returns {string[]}
 */
function timeLabels(count, stepSec, withDate) {
  const out = [];
  const d = new Date();
  for (let i = count - 1; i >= 0; i -= 1) {
    const t = new Date(d.getTime() - i * stepSec * 1000);
    out.push(
      withDate
        ? `${pad(t.getMonth() + 1)}-${pad(t.getDate())} ${pad(t.getHours())}:${pad(t.getMinutes())}`
        : `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`
    );
  }
  return out;
}

export { pad, nowHMS, createRng, walk, timeLabels };
