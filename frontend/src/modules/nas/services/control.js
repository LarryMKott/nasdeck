'use strict';

/**
 * 风扇控制视图适配层：风区卡 / 曲线编辑器 / hwmon 通道检测区数据。
 */

import * as mock from '../mock';
import {
  getCurves,
  getFanSchedule,
  getFans,
  getFcs,
  getHwmonChannels,
} from '../api/endpoints/control';
import { getTemperatures } from '../api/endpoints/monitor';
import { pick } from './shared';

/** 曲线编辑器缺省模板（后端无曲线时的预填形状；明确是模板，取自 mock 数据集会让
 * 首次「保存」把演示形状写成真实默认曲线） */
export const DEFAULT_CURVE_TEMPLATE = [
  [30, 22],
  [38, 35],
  [46, 50],
  [55, 68],
  [62, 85],
];

/** 风扇页取数：风区/曲线/FCS/硬件通道/温度传感器/静音计划 6 路并发；仅风区源不可达才演示回退
 * @returns {Promise<{data: object, live: boolean}>} */
export async function fetchFans() {
  const [zonesS, curvesS, fcsS, chansS, tempsS, schedS] = await Promise.allSettled([
    getFans(),
    getCurves(),
    getFcs(),
    getHwmonChannels(),
    getTemperatures(),
    getFanSchedule(),
  ]);
  const zones = pick(zonesS);
  if (zones === null) return { data: mock.fans, live: false }; // 仅后端不可达才演示回退

  const curves = pick(curvesS);
  const fcs = pick(fcsS);
  const channels = pick(chansS) ?? [];
  const firstCurve = (curves ?? [])[0];
  return {
    data: {
      takeover: fcs?.taken_over || zones.some((z) => z.mode !== 'auto'),
      // 时段静音计划（单路失败为 null：视图按关闭态渲染，不虚构）
      schedule: pick(schedS) ?? null,
      cards: zones.slice(0, 6).map((z) => ({
        id: z.id,
        name: z.name,
        rpm: z.current_rpm ?? 0,
        duty: Math.round(z.current_pwm_pct ?? 0),
        pwm: z.mode !== 'auto',
        mode: z.mode,
        curveId: z.curve_id,
        sensorKey: z.sensor_key,
        sensorTempC: z.sensor_temp_c,
        hwmonName: z.hwmon_name,
        pwmChannel: z.pwm_channel,
        fanChannel: z.fan_channel,
      })),
      // 未建风区的硬件通道（检测区数据源）；已建风区的通道在卡片区展示
      channels: channels.filter(
        (c) => !zones.some((z) => z.hwmon_name === c.chip && z.pwm_channel === c.pwm_channel)
      ),
      // 调速依据候选：实时温度传感器清单（不可达时为空，下拉只剩「自动 · CPU 最高温」）
      sensors: pick(tempsS) ?? [],
      curveDefault: firstCurve?.points?.length ? firstCurve.points : DEFAULT_CURVE_TEMPLATE,
      curveMeta: firstCurve
        ? {
            name: firstCurve.name,
            hysteresis_c: firstCurve.hysteresis_c,
            ramp_per_tick: firstCurve.ramp_per_tick,
          }
        : null,
      curveId: firstCurve?.id ?? null,
    },
    live: true,
  };
}
