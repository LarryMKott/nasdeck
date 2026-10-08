'use strict';

/**
 * 存储域数据模型（对齐 backend/app/schemas/storage.py，契约 §2.5-2.9）。
 */

/** 磁盘分区/子拓扑条目
 * @typedef {object} PartitionItem
 * @property {string} name 不带 /dev/ 前缀（sda1 / dm-0）
 * @property {number|null} [size_bytes]
 * @property {string|null} [fstype]
 * @property {string|null} [mountpoint]
 * @property {string} [type] lsblk TYPE（part/lvm/crypt…）
 */

/** 健康雷达维度（0-100 子分；null = 无数据）
 * @typedef {object} OracleDim
 * @property {'reallocated'|'pending'|'media'|'temp'|'wear'} key
 * @property {number|null} [value]
 */

/** 触阈值倒计时（拿得到 THRESH 且有正增速才给出）
 * @typedef {object} OracleEta
 * @property {string} metric
 * @property {number} days
 * @property {number} current
 * @property {number} threshold
 * @property {number} slope_per_day
 */

/** 硬盘健康预言（花活二期 J：smart_points 1h 桶斜率）
 * @typedef {object} DiskOracle
 * @property {number|null} score 0-100；null = 盘未采样
 * @property {'good'|'watch'|'bad'|null} [grade] good(≥85)/watch(≥60)/bad(<60)
 * @property {boolean} has_history 窗口内有无 1h 桶历史（新盘只按当前值给分）
 * @property {OracleDim[]} dims 五维雷达
 * @property {OracleEta[]} etas 触阈值倒计时
 */

/** 物理磁盘（SMART 慢采集缓存回填，health 缺省 unknown）
 * @typedef {object} DiskItem
 * @property {string} device 不带 /dev/ 前缀
 * @property {string} path
 * @property {string|null} [serial]
 * @property {string|null} [model]
 * @property {string|null} [transport]
 * @property {number} size_bytes
 * @property {string} size_human
 * @property {boolean} rotational
 * @property {string|null} [alias]
 * @property {'passed'|'warning'|'failing'|'unknown'} [health]
 * @property {number|null} [temp_c]
 * @property {number|null} [power_on_hours]
 * @property {DiskOracle|null} [oracle] 健康预言（盘未采样时 null）
 * @property {PartitionItem[]} [partitions] lsblk children 平铺
 */

/** SMART 属性行
 * @typedef {object} SmartAttribute
 * @property {number} id
 * @property {string} name
 * @property {number|null} value
 * @property {number|null} worst
 * @property {number|null} threshold
 * @property {string|null} raw
 */

/** SMART 报告（GET /storage/disks/{device}/smart）
 * @typedef {object} SmartReport
 * @property {string} device
 * @property {string|null} [model]
 * @property {string|null} [serial]
 * @property {string|null} [firmware]
 * @property {string} [health]
 * @property {number|null} [temp_c]
 * @property {number|null} [power_on_hours]
 * @property {number|null} [power_cycles]
 * @property {number|null} [nvme_percent_used]
 * @property {number|null} [nvme_media_errors]
 * @property {SmartAttribute[]} [attributes]
 * @property {boolean} [standby]
 * @property {string|null} [assessed_at]
 */

/** 阵列成员盘（storcli PD / mdadm 成员两种来源，字段可空）
 * @typedef {object} RaidMemberItem
 * @property {string|null} [slot] storcli 槽位 "E:S"；mdadm 无此字段
 * @property {string|null} [sn]
 * @property {string|null} [model]
 * @property {string|null} [state]
 * @property {string|null} [media] HDD/SSD（storcli）
 * @property {string|null} [size_human]
 * @property {string|null} [hotspare] global/dedicated（storcli）
 * @property {boolean} [failed] storcli PD 故障；mdadm 成员用 faulty
 * @property {string|null} [device] mdadm 成员分区名（sda2）
 * @property {number|null} [index] mdadm 成员序号
 * @property {boolean} [faulty] mdadm (F)
 * @property {boolean} [spare] mdadm (S)
 */

/** 阵列卷（硬 RAID VD / 软 RAID md）
 * @typedef {object} RaidVolumeItem
 * @property {'storcli'|'mdadm'} source
 * @property {string} controller
 * @property {string} volume_id
 * @property {string} name
 * @property {string} level
 * @property {number|null} [size_bytes]
 * @property {string} state
 * @property {boolean} healthy
 * @property {Record<string, unknown>} [details]
 * @property {RaidMemberItem[]} [members]
 */

/** 阵列卡控制器分量（契约 §2.8；无卡时 null）
 * @typedef {Record<string, any>} RaidController
 */

/** @typedef {object} RaidResponse
 * @property {boolean} available
 * @property {RaidVolumeItem[]} [hardware_raid]
 * @property {RaidVolumeItem[]} [software_raid]
 * @property {string|null} [storcli_error]
 * @property {RaidController|null} [controller]
 * @property {Array<Record<string, any>>} [drives] 阵列卡物理盘
 */

/** 已挂载存储卷
 * @typedef {object} VolumeItem
 * @property {string} device
 * @property {string} mount
 * @property {string} fs_type
 * @property {number} total_bytes
 * @property {number} used_bytes
 * @property {number} free_bytes
 * @property {number} percent
 * @property {string[]} opts
 */

/** 磁盘自检任务（POST/GET /storage/self-tests）
 * @typedef {object} SelfTestState
 * @property {string} device
 * @property {'short'|'long'|'conveyance'} type
 * @property {'running'|'done'|'failed'} status
 * @property {string} started_at
 * @property {string|null} [completed_at]
 * @property {number|null} [percent]
 * @property {string|null} [result]
 * @property {string|null} [error]
 */

/** SMART 趋势点（GET /storage/trend，smart_15m 采集）
 * @typedef {object} SmartTrendPoint
 * @property {string} ts 桶起点 UTC ISO
 * @property {number} value
 * @property {string|null} [raw_text] ATA 原始串
 */

/** SMART 趋势序列（days≤30 回 1h 桶，否则 1d 桶）
 * @typedef {object} SmartTrendResponse
 * @property {string} device
 * @property {string} metric
 * @property {'1h'|'1d'} granularity
 * @property {number} days
 * @property {SmartTrendPoint[]} points 按 ts 升序；无数据为空数组
 */

export {};
