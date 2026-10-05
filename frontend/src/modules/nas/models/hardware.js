'use strict';

/**
 * 硬件清单数据模型（GET /hardware，无 Pydantic schema 端点，契约 §3.7）。
 * 返回 {kind: {name, available, ...props}}：每类采集器 slow_60s 最新一轮。
 * 字段以 hardware.py 各采集器 props 为准，这里收录前端实际消费的形状。
 */

/** 主板
 * @typedef {object} HardwareBoard
 * @property {boolean} available
 * @property {string} [name]
 * @property {string} [vendor]
 * @property {string} [model]
 * @property {string} [product_name]
 * @property {string} [chipset]
 * @property {string} [bios_vendor]
 * @property {string} [bios_version]
 * @property {string} [bios_date]
 */

/** CPU
 * @typedef {object} HardwareCpu
 * @property {boolean} available
 * @property {string} [name]
 * @property {number} [physical_cores]
 * @property {number} [logical_cores]
 * @property {string} [machine]
 */

/** 内存（DIMM 槽位清单）
 * @typedef {object} HardwareMemory
 * @property {boolean} available
 * @property {boolean} [ecc]
 * @property {Array<{slot: string, size_mb: number|null}>} [dimms]
 */

/** 网卡
 * @typedef {object} HardwareNic
 * @property {boolean} available
 * @property {Array<{name: string, up: boolean, speed_mbps: number|null, ipv4: string|null}>} [nics]
 */

/** RAID 阵列卡（mode=hba 为直通卡，无硬 RAID 概念）
 * @typedef {object} HardwareRaidCard
 * @property {boolean} available
 * @property {'mega'|'hba'} [mode]
 * @property {string} [name]
 * @property {string} [driver]
 * @property {string} [note]
 * @property {string} [firmware]
 * @property {string} [cachevault]
 * @property {number} [controller_temp_c]
 * @property {number} [hotspare_count]
 * @property {'enabled'|'disabled'} [auto_copyback]
 * @property {number} [vd_count]
 * @property {number} [drive_count]
 */

/** @typedef {Record<string, Record<string, any>>} HardwareReport 全量清单（kind 为键） */

export {};
