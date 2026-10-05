'use strict';

/**
 * 硬件清单端点（契约 §3.7 /hardware 只读，无 Pydantic schema）。
 */

import { apiData } from '../client';

/** 全量硬件清单（每类采集器 slow_60s 最新一轮）
 * @returns {Promise<import('../../models/hardware').HardwareReport>} */
export function getHardware() {
  return apiData('/api/v1/hardware');
}
