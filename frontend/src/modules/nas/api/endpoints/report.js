'use strict';

/**
 * 报告域端点（契约 §3.6）：健康报告生成/下载。
 */

import { apiData } from '../client';

/** 生成健康报告（HTML；脱敏 + 60s 长超时——生成涉及全量采集）
 * @returns {Promise<import('../../models/alert').HealthReportResult>} */
export function exportHealthReport() {
  return apiData('/api/v1/report/health?redact=true', { method: 'POST', timeout: 60000 });
}
