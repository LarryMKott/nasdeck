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
 * @property {number|null} [cpu_percent]
 * @property {string|null} [mem_usage]
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

export {};
