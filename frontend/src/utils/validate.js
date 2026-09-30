'use strict';

/** 通用校验工具 */

/** @param {string} path 是否为外部链接（http/https/mailto/tel） */
export function isExternalLink(path) {
  return /^(https?:|mailto:|tel:)/.test(path);
}

/** @param {string} value 是否为合法手机号 */
export function isValidPhone(value) {
  return /^1[3-9]\d{9}$/.test(String(value ?? ''));
}
