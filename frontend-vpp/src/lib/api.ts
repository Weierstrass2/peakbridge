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

export interface Bid { hour: number; qty_kw: number; price: number; }

export interface BidResultHour {
  hour: number; qty_kw: number; bid_price: number; mcp: number;
  awarded: boolean; expected_revenue: number;
}

export interface MarketSession {
  session_id: string;
  price_source?: { engine: string; replay_year?: number | null; dataset?: string };
  delivery_date: string;
  status: 'draft' | 'submitted' | 'cleared' | 'error';
  bids: Bid[];
  deadline: string;
  seconds_to_deadline: number;
  submitted_at: string | null;
  cleared_at: string | null;
  results: {
    hours: BidResultHour[];
    awarded_hours: number;
    total_award_kwh: number;
    total_expected_revenue: number;
    avg_mcp: number;
  } | null;
}

export interface DispatchHour {
  hour: number; qty_kw: number; mcp: number; awarded: boolean;
  delivered_kwh: number; status: string; settled: boolean;
  compliance?: number; progress?: number;
}

export interface DispatchStatus {
  rtu: { seq: number; last_beat: string | null; interval_s: number };
  soc: Record<string, number>;
  market_types: { id: string; name: string; state: string }[];
  active: {
    session_id: string; delivery_date: string; time_scale: number; sim_clock: string;
    hours: DispatchHour[]; awarded_hours: number; settled_hours: number;
    energy_revenue: number; cp_revenue: number; penalties: number; net: number;
  } | null;
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
  marketSession: () => get<MarketSession>('/market/session'),
  dispatchStatus: () => get<DispatchStatus>('/dispatch/status'),
  dispatchActivate: () => post<DispatchStatus | { error: string }>('/dispatch/activate', {}),
  marketSaveBids: (bids: Bid[]) => post<MarketSession>('/market/bids', { bids }),
  marketSubmit: () => post<MarketSession>('/market/submit', {}),
  marketClear: () => post<MarketSession>('/market/clear', {}),
  marketMcpForecast: () => get<{ curve: number[] }>('/market/mcp-forecast'),
  marketHistory: () => get<{ sessions: MarketSession[] }>('/market/history'),
  issueDr: (signalType: string, value: number) =>
    post<DrEventResult>('/dr/event', {
      signal_type: signalType,
      value,
      building_id: 'building-A',
    }),
};
