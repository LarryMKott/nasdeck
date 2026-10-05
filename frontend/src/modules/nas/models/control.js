'use strict';

/**
 * 控制域数据模型（对齐 backend/app/schemas/control.py，契约 §2.15-2.18）。
 */

/** @typedef {'cpu'|'chassis'} FanLoop */

/** @typedef {'auto'|'curve'|'fixed'} FanMode */

/** 未建风区的 hwmon 硬件通道（GET /control/hwmon/channels）
 * @typedef {object} HwmonChannel
 * @property {string} chip
 * @property {string} chip_path
 * @property {number} pwm_channel
 * @property {number|null} [fan_channel]
 * @property {string|null} [label]
 * @property {number|null} [current_pwm_pct]
 * @property {number|null} [current_rpm]
 * @property {number|null} [pwm_enable]
 * @property {boolean} writable
 */

/** 创建风区请求体（POST /control/fans）
 * @typedef {object} FanZoneIn
 * @property {string} name
 * @property {FanLoop} loop
 * @property {string} hwmon_name
 * @property {number} pwm_channel
 * @property {number|null} [fan_channel]
 * @property {FanMode} mode
 * @property {number} [fixed_pwm]
 * @property {number|null} [curve_id]
 * @property {boolean} [enabled]
 * @property {string|null} [sensor_key]
 */

/** 更新风区请求体（PUT /control/fans/{id}，全部字段可选）
 * @typedef {object} FanZoneUpdate
 * @property {string} [name]
 * @property {FanMode} [mode]
 * @property {number} [fixed_pwm]
 * @property {number|null} [curve_id]
 * @property {boolean} [enabled]
 * @property {string|null} [sensor_key]
 */

/** 风区（GET /control/fans；风扇卡/总览风扇磁贴数据源）
 * @typedef {object} FanZoneItem
 * @property {number} id
 * @property {string} name
 * @property {FanLoop} loop
 * @property {string} hwmon_name
 * @property {number} pwm_channel
 * @property {FanMode} mode
 * @property {number} fixed_pwm
 * @property {number|null} curve_id
 * @property {boolean} enabled
 * @property {string|null} sensor_key
 * @property {number|null} current_pwm_pct
 * @property {number|null} current_rpm
 * @property {number|null} sensor_temp_c
 */

/** 温控曲线点 [温度°C, 占空比%]
 * @typedef {[number, number]} CurvePoint
 */

/** 创建曲线请求体（POST /control/curves）
 * @typedef {object} CurveIn
 * @property {string} name
 * @property {CurvePoint[]} points 温度严格递增、占空比 0-100
 * @property {number} [hysteresis_c]
 * @property {number} [ramp_per_tick]
 */

/** 温控曲线（GET /control/curves）
 * @typedef {object} CurveItem
 * @property {number} id
 * @property {string} name
 * @property {CurvePoint[]} points
 * @property {number} hysteresis_c
 * @property {number} ramp_per_tick
 */

/** 风扇接管服务状态（GET /control/fcs；非 Linux active=null）
 * @typedef {object} FcsStatus
 * @property {boolean} is_fnos
 * @property {string} [unit]
 * @property {boolean|null} active
 * @property {boolean} taken_over
 * @property {boolean} enabled_config
 */

export {};
