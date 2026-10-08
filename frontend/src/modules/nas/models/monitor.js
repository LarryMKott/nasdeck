'use strict';

/**
 * 监控域数据模型（对齐 backend/app/schemas/monitor.py，契约 §2.1-2.4）。
 * 仅 JSDoc typedef，无运行时代码；消费处经 import('./monitor').Type 引用。
 */

/** @typedef {'cpu'|'nvme'|'disk'|'board'|'other'} TemperatureZone */

/** @typedef {'normal'|'warm'|'hot'|'critical'} TemperatureGrade */

/** 单网卡实时吞吐（契约 §2.1）
 * @typedef {object} NetIface
 * @property {number} rx_kbps
 * @property {number} tx_kbps
 * @property {string} rx_human
 * @property {string} tx_human
 * @property {number} total_rx_mb
 * @property {number} total_tx_mb
 */

/** GPU 实时分量（AMD sysfs / NVIDIA nvidia-smi；Intel 不提供实时值，available=false）
 * @typedef {object} GpuRealtime
 * @property {boolean} available
 * @property {string} name
 * @property {number|null} percent
 * @property {number|null} vram_used_mb
 * @property {number|null} vram_total_mb
 * @property {number|null} temp_c
 * @property {number|null} [freq_mhz] intel_gpu_top 扩展：实测频率 MHz
 * @property {number|null} [freq_max_mhz] 请求频率上限 MHz
 * @property {number|null} [power_w] i915 包功耗
 * @property {number|null} [video_busy] Video 引擎（编解码）busy
 * @property {number|null} [enhance_busy] VideoEnhance 引擎（增强/缩放）busy
 * @property {string} [source]
 */

/** RAPL 实时功耗分量（Intel energy_uj 差分；非 Intel/无权限时 available=false）
 * @typedef {object} PowerRealtime
 * @property {boolean} available
 * @property {number|null} watts
 * @property {number|null} cpu_w
 * @property {number|null} dram_w
 */

/** 单盘实时 IO 速率（/proc/diskstats 差分；RAID 虚拟盘等拿不到的盘缺席）
 * @typedef {object} DiskIoDevice
 * @property {number} read_iops
 * @property {number} write_iops
 * @property {number} read_kbps
 * @property {number} write_kbps
 * @property {number} util_pct 设备忙时占比 0-100
 */

/** 实时快照（WS 1s 推送 / GET /monitor/realtime 2s 轮询降级）
 * @typedef {object} RealtimeSnapshot
 * @property {string} ts
 * @property {boolean} [available]
 * @property {number} cpu_percent
 * @property {number[]} cpu_per_core
 * @property {number|null} [cpu_freq_mhz]
 * @property {(number|null)[]} [cpu_freq_per_core] 取不到的核为 null
 * @property {number|null} [cpu_freq_max_mhz]
 * @property {number[]} load
 * @property {number} mem_used_mb
 * @property {number} mem_total_mb
 * @property {number} mem_percent
 * @property {number|null} [mem_available_mb] /proc/meminfo 口径分量，缺字段时 null
 * @property {number|null} [mem_buffers_mb]
 * @property {number|null} [mem_cached_mb]
 * @property {number|null} [mem_reserved_mb]
 * @property {number} swap_percent
 * @property {GpuRealtime|null} [gpu]
 * @property {PowerRealtime|null} [power]
 * @property {Record<string, NetIface>} net
 * @property {Record<string, number>} disk_io 键为 read_kbps/write_kbps
 * @property {Record<string, DiskIoDevice>|null} [disk_io_devices] 每盘 IO（/proc/diskstats 差分；非 Linux/无数据 null）
 * @property {number} process_count
 * @property {number} uptime_s
 */

/** 单个温度传感器读数
 * @typedef {object} TemperatureItem
 * @property {string} key
 * @property {string} chip
 * @property {string|null} [label]
 * @property {number} celsius
 * @property {TemperatureZone} zone
 * @property {TemperatureGrade} grade
 */

/** 历史采样点（落库为 UTC 无时区后缀，前端补 Z 解析）
 * @typedef {object} HistoryPoint
 * @property {string} ts
 * @property {number|null} [cpu_avg]
 * @property {number|null} [cpu_max]
 * @property {number|null} [mem_avg_mb]
 * @property {number|null} [net_avg_kbps]
 * @property {number|null} [temp_max_c]
 * @property {number|null} [gpu_avg]
 * @property {number|null} [disk_read_kbps]
 * @property {number|null} [disk_write_kbps]
 * @property {string} granularity
 */

/** @typedef {object} HistoryResponse
 * @property {HistoryPoint[]} points
 * @property {number} minutes
 * @property {string} granularity
 */

/** 历史区间统计（GET /monitor/history/stats，无 schema 端点）
 * @typedef {object} HistoryStats
 * @property {number|null} avg
 * @property {number|null} max
 * @property {number} n
 */

/** @typedef {object} DiskHealthCount
 * @property {number} passed
 * @property {number} warning
 * @property {number} failing
 * @property {number} unknown
 */

/** 总览摘要（GET /monitor/summary）
 * @typedef {object} MonitorSummary
 * @property {number} cpu_percent
 * @property {number} mem_percent
 * @property {number|null} temp_max_c
 * @property {number} uptime_s
 * @property {number} disk_total
 * @property {DiskHealthCount} disk_health
 * @property {number} raid_degraded
 */

export {};
