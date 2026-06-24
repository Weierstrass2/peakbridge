import type {
  AlertItem,
  ChartPoint,
  Charger,
  DashboardData,
  EventLogEntry,
  ReportSummary,
} from '../types';

// ── 핵심 mock 값 ──────────────────────────────────
export const grid_current = 18.4;
export const ess_soc = 72;
export const peak_active = true;
export const saved_today = 34720;
export const saved_month = 128400;

export const chargers: Charger[] = [
  { device_id: 'CH-01', current: 7.2, status: 'charging' },
  { device_id: 'CH-02', current: 6.8, status: 'charging' },
  { device_id: 'CH-03', current: 0.0, status: 'idle' },
  { device_id: 'CH-04', current: 4.1, status: 'charging' },
];

export function activeChargerCount(list: Charger[] = chargers): number {
  return list.filter((c) => c.current > 0).length;
}

export function totalChargerCurrent(list: Charger[] = chargers): number {
  return list.reduce((sum, c) => sum + c.current, 0);
}

export const mockDashboardData: DashboardData = {
  grid_current,
  ess_soc,
  ess_discharge: 5.2,
  peak_active,
  peak_threshold: 15.0,
  peak_reduction_pct: 18.5,
  chargers,
  forecast: [
    { time: '19:00', predicted: 16.2, will_exceed: true },
    { time: '19:05', predicted: 17.8, will_exceed: true },
    { time: '19:10', predicted: 18.4, will_exceed: true },
    { time: '19:15', predicted: 17.1, will_exceed: true },
    { time: '19:20', predicted: 14.2, will_exceed: false },
  ],
  today_saved_won: saved_today,
  month_saved_won: saved_month,
  co2_reduced_kg: 21,
};

function generateChartHistory(): ChartPoint[] {
  return Array.from({ length: 24 }, (_, i) => {
    const time = `${i.toString().padStart(2, '0')}:00`;
    const isPeak = i >= 10 && i <= 18;
    const base = isPeak ? 14 + Math.sin(i * 0.5) * 3 : 8 + Math.sin(i * 0.3) * 2;
    const grid = i === 14 ? grid_current : Math.max(6, base + (Math.random() - 0.5) * 2);
    const ess = isPeak && grid > 15 ? grid - 15 + Math.random() * 2 : 0;
    const chargerTotal = Math.max(0, grid - ess * 0.3);

    return {
      time,
      grid_current: Math.round(grid * 10) / 10,
      ess_discharge: Math.round(ess * 10) / 10,
      charger_total: Math.round(chargerTotal * 10) / 10,
    };
  });
}

export const mockChartHistory: ChartPoint[] = generateChartHistory();

export const mockEvents: EventLogEntry[] = [
  {
    id: '1',
    timestamp: '14:32:08',
    level: 'warning',
    message: 'Peak shaving ACTIVE — grid current 18.4A exceeds threshold 15.0A',
  },
  {
    id: '2',
    timestamp: '14:32:05',
    level: 'info',
    message: 'ESS discharge started at 5.2A (SOC 72%)',
  },
  {
    id: '3',
    timestamp: '14:31:42',
    level: 'info',
    message: 'CH-03 charging paused for load balancing',
  },
  {
    id: '4',
    timestamp: '14:28:15',
    level: 'success',
    message: 'Peak event resolved — grid current returned below threshold',
  },
  {
    id: '5',
    timestamp: '13:45:00',
    level: 'info',
    message: 'Daily savings target 80% achieved',
  },
];

export const mockAlerts: AlertItem[] = [
  {
    id: 'a1',
    type: 'peak',
    message: 'Grid current 18.4A exceeds threshold 15.0A',
    timestamp: '2026-06-24T14:32:08',
    acknowledged: false,
  },
  {
    id: 'a2',
    type: 'ess_low',
    message: 'ESS SOC below 20% — recharge recommended',
    timestamp: '2026-06-24T10:15:00',
    acknowledged: true,
  },
];

export const mockReports: ReportSummary[] = [
  {
    period: '2026-06',
    total_saved_won: saved_month,
    peak_events: 14,
    co2_reduced_kg: 21,
    avg_grid_current: 12.3,
  },
  {
    period: '2026-05',
    total_saved_won: 98200,
    peak_events: 11,
    co2_reduced_kg: 18,
    avg_grid_current: 11.8,
  },
];

export function formatKRW(amount: number): string {
  return `${amount.toLocaleString('ko-KR')}원`;
}

const mockDelay = (ms = 400) => new Promise((resolve) => setTimeout(resolve, ms));

export async function mockFetch<T>(data: T, ms = 400): Promise<T> {
  await mockDelay(ms);
  return data;
}
