import type {
  AlertItem,
  ChartPoint,
  Charger,
  DashboardData,
  EventLogEntry,
  ReportSummary,
} from '../types';

// ── 핵심 mock 값 (실측 하드웨어 스케일 0.0x A로 정렬) ──────────────
export const grid_current = 0.108;
export const ess_soc = 72;
export const peak_active = true;
export const saved_today = 34720;
export const saved_month = 128400;

export const chargers: Charger[] = [
  { device_id: 'esp32-charger-01', current: 0.036, status: 'charging' },
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
  ess_discharge: 0.036,
  peak_active,
  peak_threshold: 0.095,
  peak_reduction_pct: 18.5,
  chargers,
  forecast: [
    { time: '19:00', predicted_current: 0.096, will_exceed: true },
    { time: '19:05', predicted_current: 0.104, will_exceed: true },
    { time: '19:10', predicted_current: 0.108, will_exceed: true },
    { time: '19:15', predicted_current: 0.101, will_exceed: true },
    { time: '19:20', predicted_current: 0.084, will_exceed: false },
  ],
  today_saved_won: saved_today,
  month_saved_won: saved_month,
  co2_reduced_kg: 21,
};

function generateChartHistory(): ChartPoint[] {
  // 실측 하드웨어 스케일(0.0x A)로 생성 — 임계치 0.095A 기준
  return Array.from({ length: 24 }, (_, i) => {
    const time = `${i.toString().padStart(2, '0')}:00`;
    const isPeak = i >= 10 && i <= 18;
    const base = isPeak ? 0.085 + Math.sin(i * 0.5) * 0.02 : 0.05 + Math.sin(i * 0.3) * 0.012;
    const grid = i === 14 ? grid_current : Math.max(0.036, base + (Math.random() - 0.5) * 0.012);
    const ess = isPeak && grid > 0.095 ? grid - 0.095 + Math.random() * 0.012 : 0;
    const chargerTotal = Math.max(0, grid - ess * 0.3);

    return {
      time,
      grid_current: Math.round(grid * 1000) / 1000,
      ess_discharge: Math.round(ess * 1000) / 1000,
      charger_total: Math.round(chargerTotal * 1000) / 1000,
    };
  });
}

export const mockChartHistory: ChartPoint[] = generateChartHistory();

export const mockEvents: EventLogEntry[] = [
  {
    id: '1',
    timestamp: '14:32:08',
    level: 'warning',
    message: '피크쉐이빙 발동 — 그리드 전류 0.108A가 임계치 0.095A 초과',
  },
  {
    id: '2',
    timestamp: '14:32:05',
    level: 'info',
    message: 'ESS 방전 시작 0.036A (SOC 72%)',
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
    message: '그리드 전류 0.108A가 임계치 0.095A 초과',
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
    avg_grid_current: 0.073,
  },
  {
    period: '2026-05',
    total_saved_won: 98200,
    peak_events: 11,
    co2_reduced_kg: 18,
    avg_grid_current: 0.071,
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
