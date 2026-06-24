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
  console.log('📡 Backend reports response:', data);
  return normalizeSavingsReport(data.data);
}

export async function fetchAlerts(): Promise<AlertItem[]> {
  if (isMockMode()) {
    return mockFetch([...mockAlerts]);
  }
  const { data } = await api.get<BackendResponse<AlertItem[]>>(apiPaths.alerts());
  console.log('📡 Backend alerts response:', data);
  return data.data;
}

/** 백엔드 acknowledge 엔드포인트 확정 전 — mock 전용 */
export async function acknowledgeAlert(alertId: string): Promise<void> {
  if (isMockMode()) {
    await mockFetch(null, 200);
    return;
  }
  console.warn(`acknowledgeAlert(${alertId}): API not yet defined on backend`);
}
