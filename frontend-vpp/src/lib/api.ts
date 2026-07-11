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

export interface GridMapNode {
  id: string; name: string; x: number; y: number;
  load_kw: number; load_percent: number; status: string;
  soc?: number; available?: boolean; rating_kva?: number;
}

export interface GridMap {
  building_id: string;
  grid_current: number;
  nodes: GridMapNode[];
  edges: { from: string; to: string }[];
}

export interface LedgerEntry {
  id: string; type: string; detail: string; kwh: number; revenue: number; ts: string;
}

export interface DrEventResult {
  event_id: string; signal_type: string; value: number;
  label: string; action: string; discharge_percent?: number;
}

export interface LedgerSummary {
  today_trades: number; today_kwh: number; today_revenue: number; total_revenue: number;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${V1}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return unwrap<T>(await res.json());
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
  gridMap: () => get<GridMap>('/grid/map/building-A'),
  ledgerFull: (limit = 6) =>
    get<{ summary: LedgerSummary; entries: LedgerEntry[] }>(`/vpp/ledger?limit=${limit}`),
  drStatus: () =>
    get<{ active_event: DrEventResult | null; ven: { state: string } }>('/dr/status'),
  issueDr: (signalType: string, value: number) =>
    post<DrEventResult>('/dr/event', {
      signal_type: signalType,
      value,
      building_id: 'building-A',
    }),
};
