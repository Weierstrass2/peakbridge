import type {
  AlertItem,
  ChartPoint,
  DashboardData,
  EventLogEntry,
  ReportSummary,
  SensorReading,
} from '../types';
import { apiPaths, SENSOR_DEVICE_IDS } from '../config/apiPaths';

/** 백엔드 dashboard 응답 — chart/events는 선택 필드 */
export interface DashboardResponse extends DashboardData {
  chart_history?: ChartPoint[];
  events?: EventLogEntry[];
}

export interface SavingsReportResponse {
  today_saved_won?: number;
  month_saved_won?: number;
  co2_reduced_kg?: number;
  monthly?: ReportSummary[];
  reports?: ReportSummary[];
}

export function alertToEvent(alert: AlertItem): EventLogEntry {
  return {
    id: alert.id,
    timestamp: new Date(alert.timestamp).toLocaleTimeString('ko-KR', { hour12: false }),
    level: alert.type === 'peak' ? 'warning' : alert.type === 'ess_low' ? 'info' : 'success',
    message: alert.message,
  };
}

export function mergeChartSeries(
  grid: SensorReading[],
  ess: SensorReading[],
  charger: SensorReading[],
): ChartPoint[] {
  const byTime = new Map<string, ChartPoint>();

  const upsert = (readings: SensorReading[], key: keyof ChartPoint) => {
    for (const r of readings) {
      const time = new Date(r.timestamp).toLocaleTimeString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
      const existing = byTime.get(time) ?? {
        time,
        grid_current: 0,
        ess_discharge: 0,
        charger_total: 0,
      };
      if (key === 'grid_current') existing.grid_current = r.value;
      if (key === 'ess_discharge') existing.ess_discharge = r.value;
      if (key === 'charger_total') existing.charger_total = r.value;
      byTime.set(time, existing);
    }
  };

  upsert(grid, 'grid_current');
  upsert(ess, 'ess_discharge');
  upsert(charger, 'charger_total');

  return Array.from(byTime.values());
}

export function normalizeSavingsReport(data: SavingsReportResponse): ReportSummary[] {
  if (data.monthly?.length) return data.monthly;
  if (data.reports?.length) return data.reports;
  if (data.month_saved_won != null) {
    return [
      {
        period: new Date().toISOString().slice(0, 7),
        total_saved_won: data.month_saved_won,
        peak_events: 0,
        co2_reduced_kg: data.co2_reduced_kg ?? 0,
        avg_grid_current: 0,
      },
    ];
  }
  return [];
}
