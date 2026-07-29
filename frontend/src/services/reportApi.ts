import type { AlertItem, ReportSummary } from '../types';
import { isMockMode } from '../config/env';
import { apiPaths } from '../config/apiPaths';
import { mockAlerts, mockFetch, mockReports } from '../mock/mockData';
import { api } from './api';
import { normalizeSavingsReport, type SavingsReportResponse } from './mappers';

const V1 = '/api/v1';

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

// ── 전원 절체 이벤트 (한전 ↔ ESS) ─────────────────────────────
// fetchAlerts는 alert_type을 'peak' 하나로 뭉개므로, 절체 로그용으로
// 원본 타입을 보존해 따로 가져온다.
export interface PowerEvent {
  id: string;
  kind: 'switch_to_ess' | 'return_to_grid' | 'peak_detected';
  timestamp: string;
  gridCurrent: number | null;
  reductionPercent: number | null;
}

const POWER_EVENT_KINDS: Record<string, PowerEvent['kind']> = {
  peak_shaving_activated: 'switch_to_ess',
  peak_resolved: 'return_to_grid',
  peak_detected: 'peak_detected',
};

export async function fetchPowerEvents(limit = 8): Promise<PowerEvent[]> {
  if (isMockMode()) {
    const now = Date.now();
    return mockFetch([
      { id: 'pe-1', kind: 'switch_to_ess', timestamp: new Date(now - 40_000).toISOString(), gridCurrent: 0.108, reductionPercent: 18 },
      { id: 'pe-2', kind: 'peak_detected', timestamp: new Date(now - 45_000).toISOString(), gridCurrent: 0.108, reductionPercent: null },
      { id: 'pe-3', kind: 'return_to_grid', timestamp: new Date(now - 300_000).toISOString(), gridCurrent: 0.073, reductionPercent: null },
    ] as PowerEvent[]);
  }
  const { data } = await api.get<BackendResponse<RawAlert[]>>(apiPaths.alerts());
  return data.data
    .filter((a) => a.alert_type in POWER_EVENT_KINDS)
    .slice(0, limit)
    .map((a) => ({
      id: a.id,
      kind: POWER_EVENT_KINDS[a.alert_type],
      timestamp: a.created_at,
      gridCurrent: a.grid_current,
      reductionPercent: a.reduction_percent,
    }));
}

export async function acknowledgeAlert(alertId: string): Promise<void> {
  if (isMockMode()) {
    await mockFetch(null, 200);
    return;
  }
  await api.post(`${V1}/alerts/${alertId}/resolve`);
}
