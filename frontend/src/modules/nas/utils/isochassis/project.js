'use strict';

/**
 * 等距投影纯函数（花活三期 R1）：世界坐标 (x 右, y 纵深, z 上) → 屏幕坐标。
 * 经典 2:1 等距（cos30/sin30），渲染器与模板生成器共用，不持状态可单测。
 */

const COS30 = Math.cos(Math.PI / 6);
const SIN30 = 0.5;

/** 机位预设（花活三期 R3）：正等测 / 高俯 / 侧俯——投影系数组 {kx, ky, kz}。
 * kx/ky 为水平两轴的屏面权重，kz 为高度权重（越大越俯视）。 */
export const CAMERA_PRESETS = {
  iso: { kx: COS30, ky: SIN30, kz: 1 },
  high: { kx: 0.78, ky: 0.63, kz: 1.22 },
  side: { kx: 0.93, ky: 0.4, kz: 0.88 },
};

/**
 * 世界坐标 → 投影坐标（未含偏移与缩放）。
 * @param {number} x 右
 * @param {number} y 纵深（远离观察者方向为正）
 * @param {number} z 上
 * @returns {{x: number, y: number}}
 */
export function iso(x, y, z, p = CAMERA_PRESETS.iso) {
  return { x: (x - y) * p.kx, y: (x + y) * p.ky - z * p.kz };
}

/**
 * 盒体三可见面（顶/左/右）的投影多边形点串（SVG points 格式）。
 * 顶面最亮、左面次之、右面最暗——同一色相三种不透明度即烘焙光影。
 * @param {object} b 盒体 {x, y, z, w, d, h}
 * @returns {{top: string, left: string, right: string}} 各面 points 串
 */
export function boxFaces(b, p = CAMERA_PRESETS.iso) {
  const { x, y, z, w, d, h } = b;
  const zt = z + h;
  const top = [
    iso(x, y, zt, p),
    iso(x + w, y, zt, p),
    iso(x + w, y + d, zt, p),
    iso(x, y + d, zt, p),
  ];
  // 左面：y+d 侧（屏幕左前方），由 x/z 张成
  const left = [
    iso(x, y + d, z, p),
    iso(x + w, y + d, z, p),
    iso(x + w, y + d, zt, p),
    iso(x, y + d, zt, p),
  ];
  // 右面：x+w 侧（屏幕右前方），由 y/z 张成
  const right = [
    iso(x + w, y, z, p),
    iso(x + w, y + d, z, p),
    iso(x + w, y + d, zt, p),
    iso(x + w, y, zt, p),
  ];
  const pts = (poly) => poly.map((pt) => `${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(' ');
  return { top: pts(top), left: pts(left), right: pts(right) };
}

/**
 * 盒体深度排序键：x+y 小者远（先画），z 低者先画——画家算法。
 * @param {object} a 盒体
 * @param {object} b 盒体
 * @returns {number}
 */
export function depthCompare(a, b) {
  const da = a.x + a.y + a.z * 0.01;
  const db = b.x + b.y + b.z * 0.01;
  return da - db;
}

/**
 * 盒体顶面中心的投影点（屏幕空间文字/数字牌锚点）。
 * @param {object} b 盒体
 * @returns {{x: number, y: number}}
 */
export function boxCenter(b, p = CAMERA_PRESETS.iso) {
  return iso(b.x + b.w / 2, b.y + b.d / 2, b.z + b.h, p);
}

/**
 * 投影整体包围盒 → viewBox（留 padding）。
 * @param {{w: number, d: number, h: number}} size 场景尺寸
 * @param {number} [pad] 留白
 * @returns {{minX: number, minY: number, vw: number, vh: number}}
 */
export function sceneViewBox(size, pad = 2.5, p = CAMERA_PRESETS.iso) {
  const corners = [
    iso(0, 0, 0, p),
    iso(size.w, 0, 0, p),
    iso(0, size.d, 0, p),
    iso(size.w, size.d, 0, p),
    iso(0, 0, size.h, p),
    iso(size.w, 0, size.h, p),
    iso(0, size.d, size.h, p),
    iso(size.w, size.d, size.h, p),
  ];
  const xs = corners.map((p) => p.x);
  const ys = corners.map((p) => p.y);
  const minX = Math.min(...xs) - pad;
  const minY = Math.min(...ys) - pad;
  return { minX, minY, vw: Math.max(...xs) - minX + pad, vh: Math.max(...ys) - minY + pad };
}
