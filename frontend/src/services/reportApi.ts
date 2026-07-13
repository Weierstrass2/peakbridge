import type { AlertItem, ReportSummary } from '../types';
import { isMockMode } from '../config/env';
import { apiPaths } from '../config/apiPaths';
import { mockAlerts, mockFetch, mockReports } from '../mock/mockData';
import { api } from './api';
import { normalizeSavingsReport, type SavingsReportResponse } from './mappers';

// Backend response wrapper type
interface BackendResponse<T> {
  success: boolean;
  data: T;
}

export async function fetchReports(): Promise<ReportSummary[]> {
  if (isMockMode()) {
    return mockFetch([...mockReports]);
  }
  const { data } = await api.get<BackendResponse<SavingsReportResponse>>(apiPaths.reportsSavings());
  return normalizeSavingsReport(data.data);
}

interface RawAlert {
  id: string;
  alert_type: string;
  severity: string;
  grid_current: number | null;
  ess_soc: number | null;
  reduction_percent: number | null;
  resolved_at: string | null;
  created_at: string;
}

function alertMessage(a: RawAlert): string {
  switch (a.alert_type) {
    case 'peak_detected':
      return `피크 감지 — 그리드 ${a.grid_current?.toFixed(1) ?? '?'}A (임계치 초과)`;
    case 'peak_shaving_activated':
      return `피크쉐이빙 발동 — ESS 방전 (감축 ${a.reduction_percent?.toFixed(0) ?? '?'}%)`;
    case 'peak_resolved':
      return '피크 해제 — 정상 운전 복귀';
    case 'charger_control':
      return `충전기 수동 제어 실행 (SOC ${a.ess_soc ?? '?'}%)`;
    case 'manual_control':
      return `ESS 수동 제어 실행 (SOC ${a.ess_soc ?? '?'}%)`;
    default:
      return a.alert_type;
  }
}

export async function fetchAlerts(): Promise<AlertItem[]> {
  if (isMockMode()) {
    return mockFetch([...mockAlerts]);
  }
  const { data } = await api.get<BackendResponse<RawAlert[]>>(apiPaths.alerts());
  return data.data.map((a) => ({
    id: a.id,
    type: a.alert_type.startsWith('peak') ? ('peak' as const) : ('charger_fault' as const),
    message: alertMessage(a),
    timestamp: a.created_at,
    acknowledged: a.resolved_at != null,
  }));
}

/** 백엔드 acknowledge 엔드포인트 확정 전 — mock 전용 */
export async function acknowledgeAlert(alertId: string): Promise<void> {
  if (isMockMode()) {
    await mockFetch(null, 200);
    return;
  }
  console.warn(`acknowledgeAlert(${alertId}): API not yet defined on backend`);
}
