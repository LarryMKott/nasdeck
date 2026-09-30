'use strict';

/** 视图格式化小工具（UNRAID 稿着色规则） */

/**
 * 温度分档样式：低于 warmAt 正常、warmAt~hotAt 偏高(warm)、高于 hotAt 过热(hot)
 * @param {number} v 温度 ℃
 * @param {number} [warmAt] 偏高阈值
 * @param {number} [hotAt] 过热阈值
 * @returns {'' | 'warm' | 'hot'} 额外样式类
 */
function tempClass(v, warmAt = 40, hotAt = 50) {
  if (v >= hotAt) return 'hot';
  if (v >= warmAt) return 'warm';
  return '';
}

export { tempClass };
