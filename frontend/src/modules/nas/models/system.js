'use strict';

/**
 * 系统域数据模型（对齐 backend/app/schemas/system.py，契约 §2.10-2.14）。
 */

/** 主机信息（GET /system/info；identity store 权限判定数据源）
 * @typedef {object} SystemInfo
 * @property {string} hostname
 * @property {string} platform
 * @property {string} kernel
 * @property {string} machine
 * @property {string} python
 * @property {string} os_release
 * @property {string|null} [fnos_version]
 * @property {number} uptime_s
 * @property {string} app_version
 * @property {boolean} [is_admin] trim 形态透传 X-Trim-Isadmin；非 trim 形态恒 true
 */

/** Docker 容器条目
 * @typedef {object} ContainerItem
 * @property {string} id 12 位短 id
 * @property {string} name
 * @property {string} image
 * @property {string} state
 * @property {string} status
 * @property {string} created
 * @property {string[]} [ports]
 * @property {number|null} [cpu_percent] cgroup 增量口径；首轮采样无增量为 null
 * @property {number|null} [mem_bytes] working set 字节（花活二期 M，条形归一用）
 * @property {string|null} [mem_usage] working set 人读串（docker stats 同口径）
 * @property {number|null} [read_bps] cgroup v2 io.stat 差分读 B/s；v1/缺 io.stat null
 * @property {number|null} [write_bps] cgroup v2 io.stat 差分写 B/s
 */

/** 容器资源趋势点（1m 桶，花活二期 M）
 * @typedef {object} ContainerTrendPoint
 * @property {string} ts 桶起点 UTC
 * @property {number|null} [cpu_percent]
 * @property {number|null} [mem_mb]
 * @property {number|null} [read_kbps]
 * @property {number|null} [write_kbps]
 */

/** @typedef {object} ContainerTrendResponse
 * @property {string} name
 * @property {number} hours
 * @property {ContainerTrendPoint[]} points
 */

/** @typedef {object} DockerResponse
 * @property {boolean} available
 * @property {string|null} [reason]
 * @property {ContainerItem[]} [containers]
 */

/** 监听/连接端口条目
 * @typedef {object} PortEntry
 * @property {'tcp'|'udp'} proto
 * @property {string} local_addr
 * @property {number} local_port
 * @property {string|null} [remote_addr]
 * @property {number|null} [remote_port]
 * @property {string} status
 * @property {number|null} [pid]
 * @property {string|null} [process]
 * @property {string|null} [alias]
 */

/** 运行进程条目
 * @typedef {object} ProcessItem
 * @property {number} pid
 * @property {string} name
 * @property {string|null} [exe]
 * @property {string|null} [cmdline]
 * @property {string|null} [user]
 * @property {number} cpu_percent
 * @property {number} mem_percent
 * @property {number} mem_rss_mb
 * @property {string} status
 * @property {boolean} protected
 */

/** 运行环境自检（GET /system/env，无 schema 端点；安装期自举结果的实时呈现）
 * @typedef {object} EnvCheck
 * @property {Array<Record<string, unknown>>} [schemes] 逐域采集方案（数据源/回退/降级原因）
 * @property {{version: string, executable: string}} [python]
 * @property {{port: number, host: string, log_level: string, raw_keep_minutes: number|null, trim_auth: string}} [config]
 * @property {Array<{name: string, desc: string, ok: boolean, path: string, install: string}>} [tools]
 * @property {Array<{name: string, desc: string, loaded: boolean}>} [drivers]
 * @property {{ok: boolean, path: string, desc: string}} [storcli]
 */

/** SMART 周期巡检计划（GET/PUT /system/selftest-schedule；PUT 仅管理员）
 * @typedef {object} SelftestSchedule
 * @property {boolean} enabled
 * @property {number} weekday 0=周一 … 6=周日
 * @property {number} hour 0-23（UTC）
 * @property {'short'|'long'} type
 * @property {string|null} [last_run] ISO 日期；未跑过为 null
 */

/** 周报推送计划（GET/PUT /system/report-schedule；PUT 仅管理员）
 * @typedef {object} ReportSchedule
 * @property {boolean} enabled
 * @property {number} weekday 0=周一 … 6=周日
 * @property {number} hour 0-23（UTC）
 * @property {string|null} [last_run] ISO 日期；未推送过为 null
 */

export {};

/** 星图远端聚合（花活二期 L）
 * @typedef {object} NetworkRemote
 * @property {string} ip
 * @property {boolean} lan
 * @property {number} count
 */

/** 网络星图数据面（花活二期 L）
 * @typedef {object} NetworkMap
 * @property {number} listening
 * @property {number} established
 * @property {number} lan
 * @property {number} wan
 * @property {NetworkRemote[]} remotes 最多 24 条按连接数降序
 */
