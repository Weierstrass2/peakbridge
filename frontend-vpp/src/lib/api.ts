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
  forecast_hi?: number;
  forecast_lo?: number;
  smp: number;
  dr_active: boolean;
  discharge_percent: number;
}

export interface WeatherPoint {
  region: string;
  lat: number;
  lon: number;
  temperature: number;
  wind_speed: number;
  solar_radiation: number;
  solar_estimated?: boolean;
  alert: string | null;
}

export interface WeatherOverlay {
  points: WeatherPoint[];
  updated_at: string;
  source?: string;
}

export interface Portfolio {
  total_capacity_kwh: number;
  available_flexibility_kw: number;
  building_count: number;
  buildings: {
    building_id: string; ess_capacity: number; current_soc: number;
    usable_kwh: number; available_kw: number; live?: boolean;
    soh?: number; pcs_temp?: number; pcs_eff?: number; link_ms?: number;
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

/** 전략 카탈로그 1건 — 백테스트 성과가 함께 온다 (없으면 null) */
export interface StrategyInfo {
  name: string;
  family: string;
  description: string;
  active: boolean;
  daily_mean_won: number | null;
  sharpe: number | null;
  max_drawdown_won: number | null;
  hit_rate: number | null;
  fill_rate: number | null;
}

/* ── 트레이딩 데스크 타입 ── */

export interface DeskOverview {
  portfolio: { power_kw: number; usable_kwh: number; units: number };
  equity_won: number;
  sessions: number;
  current_sharpe: number | null;
  current_drawdown_won: number;
  var95_won: number;
  cvar95_won: number;
  kill_switch: boolean;
  reason: string;
  active_strategy: string;
  totals: Record<string, number>;
}

export interface Fill {
  id: string;
  date: string;
  hour: number;
  strategy: string;
  side: string;
  qty_kw: number;
  delivered_kw: number;
  bid_price: number;
  clear_price: number;
  slippage: number;
  value_won: number;
  status: string;
}

export interface DeskPnl {
  sessions: {
    date: string;
    strategy: string;
    net_won: number;
    attribution: Record<string, number>;
    volume: Record<string, number | null>;
  }[];
  totals: Record<string, number>;
  rolling: {
    points: { i: number; pnl: number; equity: number; drawdown: number; sharpe: number | null }[];
    current_sharpe?: number | null;
    current_drawdown?: number;
    max_drawdown?: number;
    equity_won?: number;
  };
}

export interface DeskTca {
  avg_slippage?: number;
  hit_ratio?: number;
  captured_won?: number;
  missed_value_won?: number;
  sessions?: number;
}

export interface ForecastQuality {
  samples?: number;
  mape_pct?: number;
  rmse?: number;
  bias?: number;
  pinball_loss?: number;
  verdict?: string;
  calibration?: { bucket: number; forecast_mean: number; actual_mean: number; gap: number }[];
}

export interface HedgeDecisionRow {
  hour: number;
  obligation_kw: number;
  deliverable_kw: number;
  shortfall_kw: number;
  rt_price: number;
  penalty_price: number;
  action: 'hedge' | 'accept_penalty' | 'none';
  cost_won: number;
  saved_won: number;
  reason: string;
}

export interface HedgePlan {
  strategy?: string;
  available_kwh?: number;
  available_ratio?: number;
  decisions: HedgeDecisionRow[];
  summary: {
    obligation_kwh?: number;
    deliverable_kwh?: number;
    shortfall_kwh?: number;
    hedged_kwh?: number;
    hedge_cost_won?: number;
    penalty_avoided_won?: number;
    penalty_paid_won?: number;
    hedge_count?: number;
    coverage_after?: number;
  };
  comparison?: {
    without_hedge_won: number;
    with_hedge_won: number;
    improvement_won: number;
    hedge_cost_won: number;
    coverage_after: number;
  };
}

export interface StochasticPlan {
  scenarios?: number;
  expected_won?: number;
  cvar5_won?: number;
  var5_won?: number;
  worst_won?: number;
  best_won?: number;
  loss_prob?: number;
  active_hours?: number;
  bids?: Bid[];
}

export interface SettlementLine {
  item: string;
  label: string;
  ours_won: number;
  theirs_won: number;
  diff_won: number;
  diff_pct: number;
  verdict: 'match' | 'minor' | 'dispute';
}

export interface SettlementCheck {
  strategy?: string;
  error_mode?: string;
  status?: 'match' | 'minor' | 'dispute' | 'error';
  checks: SettlementLine[];
  underpaid_won?: number;
  overpaid_won?: number;
  dispute_items?: string[];
  summary?: string;
}

export interface OverfitReport {
  best_strategy?: string;
  test_days?: number;
  deflated_sharpe?: {
    observed_sharpe_annual?: number;
    trials?: number;
    expected_max_sharpe_annual?: number;
    deflated_sharpe_prob?: number;
    significant?: boolean;
    skew?: number;
    kurtosis?: number;
    samples?: number;
    verdict?: string;
  };
  pbo?: {
    pbo?: number;
    combinations?: number;
    splits?: number;
    strategies?: number;
    verdict?: string;
  };
}

export interface RiskCheckRow {
  code: string;
  severity: 'ok' | 'warn' | 'breach';
  message: string;
  value: number;
  limit: number;
}

export interface PreTrade {
  status: 'ok' | 'warn' | 'breach';
  blocked: boolean;
  kill_switch: boolean;
  reason: string;
  checks: RiskCheckRow[];
  var95_won: number;
  cvar95_won: number;
  stress: { scenario: string; description: string; pnl_won: number; delta_won: number; energy_kwh: number }[];
  portfolio: { power_kw: number; usable_kwh: number };
  strategy?: string;
  bids?: Bid[];
}

export interface StrategyBidResult {
  strategy: string;
  family: string;
  description: string;
  backtest: {
    daily_mean_won: number | null;
    sharpe: number | null;
    max_drawdown_won: number | null;
    test_days: number | null;
  };
  usable_kwh: number;
  power_kw: number;
  bids: Bid[];
}

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
    shadow?: { basis: string; human_net: number; ai_net: number; opportunity_cost: number } | null;
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
    cumulative?: { awarded_kwh: number; delivered_kwh: number; rate: number; defended_won: number };
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
  by_type?: Record<string, number>;
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

/* ── 제주 실시간시장 ──────────────────────────────────── */

export interface JejuRow {
  strategy: string;
  label: string;
  daily_mean_won: number;
  annual_won: number;
  sharpe: number | null;
  max_drawdown_won: number;
  hit_rate: number;
  worst_day_won: number;
  discharge_kwh: number;
  charge_kwh: number;
  free_kwh: number;
  free_share: number;
  revenue_won: number;
  charge_cost_won: number;
  degradation_won: number;
  margin_per_kwh: number | null;
  avg_curtail_slots: number;
  days: number;
}

export interface JejuLeaderboard {
  market: string;
  disclaimer: string;
  asset: { power_kw: number; capacity_kwh: number; degradation_won: number; round_trip: number };
  leaderboard: JejuRow[];
}

export interface JejuSensitivity {
  rows: {
    scenario: string;
    must_run_mw: number;
    free_share: number;
    charge_unit_won: number;
    margin_per_kwh: number | null;
    annual_won: number;
  }[];
  inland_reference: {
    label: string;
    charge_unit_won: number;
    peak_won: number;
    var_cost_won: number;
    margin_per_kwh: number;
  };
  verdict: string;
}

export interface JejuSiteCompare {
  sites: {
    site: string;
    behind_meter: boolean;
    price_basis: string;
    rows: {
      strategy: string;
      label: string;
      annual_won: number;
      margin_per_kwh: number | null;
      free_share: number;
      hit_rate: number;
    }[];
  }[];
  insight: string;
}

/* ── 시장 프로파일 · 데이터 출처 ────────────────────────── */

export interface RevenueStream {
  key: string;
  label: string;
  available: boolean;
  basis: string;
  note: string;
}

export interface MarketProfile {
  key: string;
  name: string;
  region: string;
  role: string;
  bidding: string;
  price_use: string;
  settlement: string;
  penalty: string;
  status: string;
  streams: RevenueStream[];
  available_streams: string[];
}

export interface MarketProfileCompare {
  profiles: MarketProfile[];
  comparison: { item: string; inland: string; jeju: string }[];
  shared_engine: string[];
  note: string;
}

export interface DataSource {
  enabled: boolean;
  source: string;          // kpx | replay
  label: string;
  region: string;
  csv_exists: boolean;
  smp_cached: boolean;
  last_error: string;
  hint: string;
  calibration?: string | null;
  region_scale?: number | null;
  smp_today?: number[] | null;
}

/* ── 피크 예약 ──────────────────────────────────────────── */

export interface PeakReservation {
  reserved_kwh: number;
  blackout_hours: number[];
  peak_hours: number[];
  expected_peak_kw: number;
  month_peak_kw: number;
  headroom_kw: number;
  shave_kw: number;
  peak_value_won_per_kwh: number;
  renews_month_peak: boolean;
  detail: { hour: number; demand_kw: number; over_kw: number; shave_kw: number }[];
  comparison: {
    market_won_per_kwh: number;
    peak_won_per_kwh: number;
    ratio: number | null;
    verdict: string;
  };
  demand_kw: number[];
  forecast: number[];
  usable_kwh: number;
  sellable_kwh: number;
  contract_kw: number;
}

/* ── 제주 플러스 DR (실측 기반) ─────────────────────────── */

export interface PlusDrRow {
  strategy: string;
  label: string;
  description: string;
  events: number;
  cleared_mwh: number;
  delivered_mwh: number;
  delivery_rate: number;
  net_won: number;
}

export interface PlusDrReport {
  market: string;
  facts: {
    clearing_rate: number;
    delivery_rate: number;
    delivery_pct_median: number;
    full_delivery_share: number;
    smp_mean: number;
    smp_min: number;
    event_days_per_year: number;
    curtail_days_per_year: number;
    event_hours: number[];
    avg_cleared_per_event_mwh: number;
    _loaded: boolean;
    _records?: number;
    _years?: string[];
  };
  assumption: {
    incentive_won_per_kwh: number;
    tou_peak_won: number;
    tou_off_won: number;
    base_rate_won_per_kw: number;
    breakeven_managed: number;
    breakeven_unmanaged: number;
    note: string;
  };
  fleet: { sites: number; power_mw: number; usable_mwh: number };
  leaderboard: PlusDrRow[];
  edge: { baseline_delivery: number; ours_delivery: number; gap: number | null };
  thesis: string;
  disclaimer: string;
}

/* ── 제주 운영 시뮬레이터 ───────────────────────────────── */

export interface JejuSite {
  id: string; name: string;
  contract_kw: number; capacity_kwh: number; soc: number;
  room_kwh: number; base_load_kw: number;
  today_peak_kw: number; month_peak_kw: number;
  headroom_kw: number; max_charge_kw: number; online: boolean; live?: boolean;
}

export interface JejuEvent {
  ts: string; hour: number;
  request_mwh: number; request_kwh: number;
  curtail_mw: number; duration_min: number;
  status: string; tou_won: number; is_peak_hour: boolean;
}

export interface JejuOpsState {
  facts: {
    clearing_rate: number; market_delivery: number;
    delivery_median: number; avg_cleared_mwh: number;
    event_hours: number[]; curtail_days_per_year: number; loaded: boolean;
  };
  sites: JejuSite[];
  event: JejuEvent | null;
  fleet: { count: number; online: number; room_kwh: number; safe_charge_kw: number; avg_soc: number };
  log: { ts: string; level: string; msg: string }[];
  history: { ts: string; hour: number; mode: string; delivery_rate: number; net_won: number; peak_penalty_won: number }[];
}

export interface JejuResult {
  mode?: string;
  rows: {
    site: string; name: string;
    ordered_kw: number; delivered_kw: number; rate: number;
    load_before_kw: number; load_after_kw: number; guard_kw: number;
    peak_over_kw: number; peak_penalty_won: number;
  }[];
  ordered_kwh: number; delivered_kwh: number; delivery_rate: number;
  incentive_won: number; energy_cost_won: number; recovery_won: number;
  degradation_won: number; peak_penalty_won: number; net_won: number;
  sites_over_peak: number; coverage: number;
  need_kwh?: number; incentive_assumed?: number; market_delivery_rate?: number;
}

export interface JejuAssetSide {
  label: string;
  capex_won: number;
  need_capacity_kwh: number;
  degradation_won?: number;
  discount_cost_won?: number;
  event_net_won: number;
  year_net_won: number;
  payback_years: number | null;
}

export interface JejuAssetCompare {
  absorbed_kwh: number;
  events_per_year: number;
  incentive_assumed: number;
  ev_discount_assumed: number;
  capex_per_kwh_assumed: number;
  ess_owned: JejuAssetSide;
  ev_fleet: JejuAssetSide;
  verdict: string;
  note: string;
  error?: string;
}

export interface JejuCompare {
  need_kwh: number; hour: number; is_peak_hour: boolean;
  incentive_assumed: number;
  even: JejuResult; peak: JejuResult;
  gap_won: number; verdict: string;
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
  opsAlarms: () => get<{ unack: number; items: { id: string; ts: string; severity: string; source: string; msg: string; ack: boolean }[] }>('/ops/alarms'),
  opsAck: (id: string, actor = 'operator') => post<{ acked: boolean }>(`/ops/alarms/${id}/ack?actor=${encodeURIComponent(actor)}`, {}),
  opsAudit: () => get<{ entries: { ts: string; actor: string; action: string; detail: string }[] }>('/ops/audit'),
  streamHistory: () => get<{ points: { ts: string; total_output_kw: number; demand_kw: number; forecast_kw: number; smp: number }[] }>('/vpp/stream/history'),
  marketRt: () => get<{ slot: string; seconds_left: number; rt_price: number; dam_ref: number }>('/market/rt'),
  marketRtSell: (qty: number) => post<{ filled: boolean; slot: string; fill_price: number; revenue: number }>('/market/rt/sell', { qty_kw: qty }),
  vppContracts: () => get<{
    contracts: { building_id: string; name: string; type: string; site_share: number; platform_share: number; term: string; resources: string; status: string }[];
    settlement_split: { total_revenue: number; site_payout: number; platform_revenue: number; avg_platform_share: number };
  }>('/vpp/contracts'),
  weatherOverlay: () => get<WeatherOverlay>('/weather/map-overlay', 15000),
  demoReset: () => post<{ reset: boolean }>('/simulation/demo-reset', {}),
  demoDay: () => post<{ status: string; steps: string[] }>('/simulation/demo-day', {}),
  opsRisk: () => get<{ status: string; usable_kwh: number; obligation_kwh: number; coverage: number }>('/ops/risk'),
  dispatchActivate: () => post<DispatchStatus | { error: string }>('/dispatch/activate', {}),
  marketSaveBids: (bids: Bid[]) => post<MarketSession>('/market/bids', { bids }),
  marketSubmit: () => post<MarketSession>('/market/submit', {}),
  marketClear: () => post<MarketSession>('/market/clear', {}),
  marketMcpForecast: () => get<{ curve: number[] }>('/market/mcp-forecast'),
  marketHistory: () => get<{ sessions: MarketSession[] }>('/market/history'),
  marketAiBids: () => get<{ model: string; usable_kwh: number; eval: { ai: number; naive: number }; bids: Bid[] }>('/market/ai-bids'),

  // ── 트레이딩 데스크 ──
  deskOverview: () => get<DeskOverview>('/desk/overview'),
  deskBlotter: (limit = 40) => get<{ fills: Fill[] }>(`/desk/blotter?limit=${limit}`),
  deskPnl: () => get<DeskPnl>('/desk/pnl'),
  deskTca: () => get<DeskTca>('/desk/tca'),
  deskForecastQuality: () => get<ForecastQuality>('/desk/forecast-quality'),
  deskRisk: () => get<{ limits: Record<string, number>; kill_switch: boolean; reason: string }>('/desk/risk'),
  deskPreTrade: (strategy?: string) =>
    get<PreTrade>(`/desk/pre-trade${strategy ? `?strategy=${encodeURIComponent(strategy)}` : ''}`, 12000),
  deskSeed: (strategy = 'zscore', days = 30) =>
    post<{ seeded: number; fills: number }>('/desk/seed', { strategy, days }),
  deskHedge: (availableRatio = 0.7, strategy?: string) =>
    get<HedgePlan>(
      `/desk/hedge?available_ratio=${availableRatio}${strategy ? `&strategy=${encodeURIComponent(strategy)}` : ''}`,
      12000,
    ),
  deskStochastic: (scenarios = 200) => get<StochasticPlan>(`/desk/stochastic?scenarios=${scenarios}`, 15000),
  deskSettlement: (errorMode = 'underpay') =>
    get<SettlementCheck>(`/desk/settlement?error_mode=${errorMode}`, 12000),
  deskOverfit: (days = 60) => get<OverfitReport>(`/desk/overfit?days=${days}`, 30000),
  deskKillReset: () => post<{ kill_switch: boolean }>('/desk/kill-switch/reset', {}),
  deskReset: () => post<{ reset: boolean }>('/desk/reset', {}),

  // ── 제주 실시간시장 ──
  jejuLeaderboard: (days = 180, spreadScale = 0.41, behindMeter = false) =>
    get<JejuLeaderboard>(
      `/market/jeju/leaderboard?days=${days}&spread_scale=${spreadScale}` +
        `&behind_meter=${behindMeter}`, 30000,
    ),
  peakReservation: (contractKw = 200, monthPeakKw = 0, lookbackMonths = 1) =>
    get<PeakReservation>(
      `/market/peak-reservation?contract_kw=${contractKw}` +
        `&month_peak_kw=${monthPeakKw}&lookback_months=${lookbackMonths}`, 15000,
    ),

  // ── 제주 운영 시뮬레이터 ──
  jejuOpsState: () => get<JejuOpsState>('/jeju-ops/state'),
  jejuOpsEvent: (hour?: number) =>
    post<JejuOpsState>('/jeju-ops/event', hour === undefined ? {} : { hour }),
  jejuOpsAssetCompare: (incentive = 120, evDiscount = 40) =>
    get<JejuAssetCompare>(
      `/jeju-ops/asset-compare?incentive=${incentive}&ev_discount=${evDiscount}`, 15000),
  jejuOpsCompare: (incentive = 120) =>
    get<JejuCompare>(`/jeju-ops/compare?incentive=${incentive}`, 15000),
  jejuOpsDispatch: (mode: 'peak' | 'even', incentive = 120) =>
    post<JejuResult>('/jeju-ops/dispatch', { mode, incentive }),
  jejuOpsAdvance: () => post<JejuOpsState>('/jeju-ops/advance', {}),
  jejuOpsReset: (sites = 12) => post<JejuOpsState>(`/jeju-ops/reset?sites=${sites}`, {}),

  // ── 시장 프로파일 · 데이터 출처 ──
  marketProfiles: () => get<MarketProfileCompare>('/market/profiles'),
  marketProfile: (key?: string) =>
    get<MarketProfile>(`/market/profile${key ? `?key=${encodeURIComponent(key)}` : ''}`),
  dataSource: () => get<DataSource>('/market/data-source', 12000),

  jejuPlusDr: (incentive = 120, sites = 100) =>
    get<PlusDrReport>(`/market/jeju/plusdr?incentive=${incentive}&sites=${sites}`, 20000),

  jejuSiteCompare: (days = 120) =>
    get<JejuSiteCompare>(`/market/jeju/site-compare?days=${days}`, 30000),
  jejuSensitivity: (days = 180) =>
    get<JejuSensitivity>(`/market/jeju/sensitivity?days=${days}`, 30000),

  // ── 전략 라이브러리 (퀀트 백테스트 결과 기반) ──
  strategies: () =>
    get<{ active: string; strategies: StrategyInfo[] }>('/market/strategies'),
  strategyActivate: (name: string) =>
    post<{ active: string }>('/market/strategies/activate', { name }),
  strategyBids: (name?: string) =>
    get<StrategyBidResult>(
      `/market/strategy-bids${name ? `?strategy=${encodeURIComponent(name)}` : ''}`,
    ),
  issueDr: (signalType: string, value: number) =>
    post<DrEventResult>('/dr/event', {
      signal_type: signalType,
      value,
      building_id: 'building-A',
    }),
};
