'use strict';

/**
 * 风扇控制视图适配层：风区卡 / 曲线编辑器 / hwmon 通道检测区数据。
 */

import * as mock from '../mock';
import { getCurves, getFans, getFcs, getHwmonChannels } from '../api/endpoints/control';
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

/** 风扇页取数：风区/曲线/FCS/硬件通道 4 路并发；仅风区源不可达才演示回退
 * @returns {Promise<{data: object, live: boolean}>} */
export async function fetchFans() {
  const [zonesS, curvesS, fcsS, chansS] = await Promise.allSettled([
    getFans(),
    getCurves(),
    getFcs(),
    getHwmonChannels(),
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
      cards: zones.slice(0, 6).map((z) => ({
        id: z.id,
        name: z.name,
        rpm: z.current_rpm ?? 0,
        duty: Math.round(z.current_pwm_pct ?? 0),
        pwm: z.mode !== 'auto',
        hwmonName: z.hwmon_name,
        pwmChannel: z.pwm_channel,
        fanChannel: z.fan_channel,
      })),
      // 未建风区的硬件通道（检测区数据源）；已建风区的通道在卡片区展示
      channels: channels.filter(
        (c) => !zones.some((z) => z.hwmon_name === c.chip && z.pwm_channel === c.pwm_channel)
      ),
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
