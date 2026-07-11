/** 백엔드 API 클라이언트 — 콘솔 전용 경량 fetch 래퍼. */

const BASE =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ??
  'https://peakbridge-production.up.railway.app';

const V1 = `${BASE}/api/v1`;

function unwrap<T>(payload: unknown): T {
  const p = payload as { success?: boolean; data?: unknown };
  if (p && typeof p === 'object' && 'success' in p && 'data' in p) return p.data as T;
  return payload as T;
}

export interface StreamSnapshot {
  ts: string;
  buildings: { id: string; output_kw: number; soc: number; live: boolean }[];
  total_output_kw: number;
  demand_kw: number;
  forecast_kw: number;
  smp: number;
  dr_active: boolean;
  discharge_percent: number;
}

export interface Portfolio {
  total_capacity_kwh: number;
  available_flexibility_kw: number;
  building_count: number;
  buildings: {
    building_id: string; ess_capacity: number; current_soc: number;
    usable_kwh: number; available_kw: number; live?: boolean;
  }[];
}

export interface LedgerSummary {
  today_trades: number; today_kwh: number; today_revenue: number; total_revenue: number;
}

async function get<T>(path: string, timeoutMs = 8000): Promise<{ data: T; latencyMs: number }> {
  const t0 = performance.now();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${V1}${path}`, { signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    return { data: unwrap<T>(json), latencyMs: Math.round(performance.now() - t0) };
  } finally {
    clearTimeout(timer);
  }
}

export const consoleApi = {
  base: BASE,
  stream: () => get<StreamSnapshot>('/vpp/stream'),
  portfolio: () => get<Portfolio>('/vpp/portfolio'),
  ledger: () => get<{ summary: LedgerSummary; entries: unknown[] }>('/vpp/ledger?limit=1'),
};
