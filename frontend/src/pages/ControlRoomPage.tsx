import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Area, AreaChart, CartesianGrid, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { api } from '../services/api';
import { unwrap } from '../services/energyApi';
import { vppApi, type DrEvent } from '../services/vppApi';

const V1 = '/api/v1';
const BUFFER = 60;

interface StreamPoint {
  ts: string;
  A: number; B: number; C: number;
  total: number; demand: number; forecast: number; smp: number;
  drActive: boolean;
}

interface MapNode {
  id: string; name: string; x: number; y: number;
  load_percent: number; status: string; soc?: number; available?: boolean;
}

interface LedgerEntry {
  id: string; type: string; detail: string; kwh: number; revenue: number; ts: string;
}

const NODE_COLOR: Record<string, string> = {
  '정상': '#34D399', '경고': '#FBBF24', '과부하': '#EF4444',
  '대기': '#3B82F6', '미연결': '#475569',
};

export default function ControlRoomPage() {
  const [points, setPoints] = useState<StreamPoint[]>([]);
  const [latest, setLatest] = useState<StreamPoint | null>(null);
  const [mapNodes, setMapNodes] = useState<MapNode[]>([]);
  const [mapEdges, setMapEdges] = useState<{ from: string; to: string }[]>([]);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [ledgerSummary, setLedgerSummary] = useState({ today_trades: 0, today_kwh: 0, today_revenue: 0 });
  const [events, setEvents] = useState<DrEvent[]>([]);
  const [flexKw, setFlexKw] = useState(135);
  const [accuracy, setAccuracy] = useState(96.4);
  const [clock, setClock] = useState(new Date());
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const dischargePct = useRef(0);

  // 시계
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // 실시간 스트림 (3초)
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const d = unwrap<{
          ts: string; buildings: { id: string; output_kw: number }[];
          total_output_kw: number; demand_kw: number; forecast_kw: number;
          smp: number; dr_active: boolean; discharge_percent: number;
        }>((await api.get(`${V1}/vpp/stream`)).data);
        if (!alive) return;
        dischargePct.current = d.discharge_percent;
        const p: StreamPoint = {
          ts: d.ts,
          A: d.buildings[0]?.output_kw ?? 0,
          B: d.buildings[1]?.output_kw ?? 0,
          C: d.buildings[2]?.output_kw ?? 0,
          total: d.total_output_kw,
          demand: d.demand_kw,
          forecast: d.forecast_kw,
          smp: d.smp,
          drActive: d.dr_active,
        };
        setLatest(p);
        setPoints((prev) => [...prev.slice(-(BUFFER - 1)), p]);
      } catch { /* 폴링 실패 무시 */ }
    };
    tick();
    const t = setInterval(tick, 3000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  // 계통도 (15초)
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const d = unwrap<{ nodes: MapNode[]; edges: { from: string; to: string }[] }>(
          (await api.get(`${V1}/grid/map/building-A`)).data,
        );
        if (!alive) return;
        setMapNodes(d.nodes);
        setMapEdges(d.edges);
      } catch { /* noop */ }
    };
    load();
    const t = setInterval(load, 15_000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  // 장부 + 이력 + 유연성 + 정확도 (10초)
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const l = unwrap<{ summary: typeof ledgerSummary & { total_revenue: number }; entries: LedgerEntry[] }>(
          (await api.get(`${V1}/vpp/ledger`)).data,
        );
        if (alive) { setLedger(l.entries); setLedgerSummary(l.summary); }
      } catch { /* noop */ }
      try {
        const h = await vppApi.getDrHistory();
        if (alive) setEvents(h.events);
      } catch { /* noop */ }
      try {
        const p = await vppApi.getPortfolio();
        if (alive) setFlexKw(p.available_flexibility_kw);
      } catch { /* noop */ }
      try {
        const m = unwrap<{ mae: number | null }>((await api.get(`${V1}/energy/model-info`)).data);
        if (alive && m.mae) setAccuracy(Math.max(80, Math.min(99.9, 100 - m.mae * 4)));
      } catch { /* noop */ }
    };
    load();
    const t = setInterval(load, 10_000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const act = async (fn: () => Promise<unknown>, label: string) => {
    setBusy(true);
    try { await fn(); setBanner(`✅ ${label} 실행됨`); }
    catch { setBanner(`❌ ${label} 실패`); }
    finally { setBusy(false); setTimeout(() => setBanner(null), 4000); }
  };

  const nodeById = (id: string) => mapNodes.find((n) => n.id === id);
  const drActive = latest?.drActive ?? false;
  const activeUnits = Math.round((dischargePct.current / 100) * 20);

  const tickerItems = [
    ...ledger.slice(0, 4).map((e) => `${e.ts.slice(11, 19)} [${e.type}] ${e.detail} → ₩${Math.round(e.revenue).toLocaleString()}`),
    ...events.slice(0, 4).map((ev) => `${new Date(ev.issued_at).toLocaleTimeString('ko-KR', { hour12: false })} [발령] ${ev.label}`),
  ];

  return (
    <div className="min-h-screen bg-[#05080F] text-[#E2E8F0] flex flex-col font-sans">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-[#1E293B] px-6 py-3 shrink-0">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-bold tracking-wide text-[#F1F5F9]">
            PeakBridge <span className="text-[#3B82F6]">VPP 통합 관제센터</span>
          </h1>
          <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
            drActive ? 'bg-[#F97316]/15 text-[#F97316]' : 'bg-[#34D399]/15 text-[#34D399]'
          }`}>
            <span className={`h-1.5 w-1.5 rounded-full ${drActive ? 'bg-[#F97316] animate-ping' : 'bg-[#34D399]'}`} />
            {drActive ? 'DR 이벤트 대응 중' : '계통 정상'}
          </span>
        </div>
        <div className="flex items-center gap-4">
          <span className="font-mono text-xl tabular-nums text-[#F1F5F9]">
            {clock.toLocaleTimeString('ko-KR', { hour12: false })}
          </span>
          <button
            onClick={() => document.documentElement.requestFullscreen?.()}
            className="rounded-lg border border-[#334155] px-3 py-1.5 text-xs text-[#94A3B8] hover:bg-[#1E293B]"
          >⛶ 전체화면</button>
          <Link to="/vpp" className="rounded-lg border border-[#334155] px-3 py-1.5 text-xs text-[#94A3B8] hover:bg-[#1E293B]">
            닫기
          </Link>
        </div>
      </header>

      {/* KPI strip */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-px bg-[#1E293B] border-b border-[#1E293B] shrink-0">
        {[
          { l: '총 VPP 출력', v: `${(latest?.total ?? 0).toFixed(1)} kW`, c: 'text-[#3B82F6]' },
          { l: '가용 유연성', v: `${flexKw.toLocaleString()} kW`, c: 'text-[#F1F5F9]' },
          { l: 'SMP 현재가', v: `${(latest?.smp ?? 0).toFixed(1)}원`, c: 'text-[#FBBF24]' },
          { l: '금일 거래', v: `${ledgerSummary.today_trades}건 · ${ledgerSummary.today_kwh}kWh`, c: 'text-[#F1F5F9]' },
          { l: '금일 수익', v: `₩${Math.round(ledgerSummary.today_revenue).toLocaleString()}`, c: 'text-[#34D399]' },
          { l: '예측 정확도', v: `${accuracy.toFixed(1)}%`, c: 'text-[#A78BFA]' },
        ].map((k) => (
          <div key={k.l} className="bg-[#05080F] px-4 py-3">
            <p className="text-[10px] uppercase tracking-widest text-[#64748B]">{k.l}</p>
            <p className={`mt-0.5 font-mono text-lg font-bold tabular-nums ${k.c}`}>{k.v}</p>
          </div>
        ))}
      </div>

      {/* Main grid */}
      <div className="flex-1 grid grid-cols-12 gap-3 p-3 min-h-0">
        {/* Left: charts */}
        <div className="col-span-12 lg:col-span-5 flex flex-col gap-3 min-h-0">
          <div className="flex-1 rounded-xl border border-[#1E293B] bg-[#0A0F1A] p-3 min-h-[180px]">
            <p className="text-xs font-semibold text-[#94A3B8] mb-1">단지별 VPP 출력 (kW) — 실시간</p>
            <ResponsiveContainer width="100%" height="88%">
              <AreaChart data={points} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
                <XAxis dataKey="ts" tick={{ fontSize: 9, fill: '#475569' }} interval={14} />
                <YAxis tick={{ fontSize: 9, fill: '#475569' }} />
                <Tooltip contentStyle={{ backgroundColor: '#0F172A', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                <Area type="monotone" dataKey="A" stackId="1" stroke="#34D399" fill="#34D399" fillOpacity={0.5} name="A단지(실측)" isAnimationActive={false} />
                <Area type="monotone" dataKey="B" stackId="1" stroke="#3B82F6" fill="#3B82F6" fillOpacity={0.4} name="B단지" isAnimationActive={false} />
                <Area type="monotone" dataKey="C" stackId="1" stroke="#A78BFA" fill="#A78BFA" fillOpacity={0.4} name="C단지" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="flex-1 rounded-xl border border-[#1E293B] bg-[#0A0F1A] p-3 min-h-[180px]">
            <p className="text-xs font-semibold text-[#94A3B8] mb-1">
              SMP 가격(원/kWh) · 수요 예측 vs 실측 (kW)
            </p>
            <ResponsiveContainer width="100%" height="88%">
              <LineChart data={points} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
                <XAxis dataKey="ts" tick={{ fontSize: 9, fill: '#475569' }} interval={14} />
                <YAxis tick={{ fontSize: 9, fill: '#475569' }} />
                <Tooltip contentStyle={{ backgroundColor: '#0F172A', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                <Line type="monotone" dataKey="smp" stroke="#FBBF24" dot={false} strokeWidth={2} name="SMP" isAnimationActive={false} />
                <Line type="monotone" dataKey="demand" stroke="#3B82F6" dot={false} strokeWidth={1.5} name="수요 실측" isAnimationActive={false} />
                <Line type="monotone" dataKey="forecast" stroke="#A78BFA" dot={false} strokeWidth={1.5} strokeDasharray="5 3" name="AI 예측" isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Center: one-line diagram */}
        <div className="col-span-12 lg:col-span-4 rounded-xl border border-[#1E293B] bg-[#0A0F1A] p-3 min-h-[300px]">
          <p className="text-xs font-semibold text-[#94A3B8] mb-1">단지 계통도 — building-A (실측)</p>
          <svg viewBox="0 0 100 100" className="w-full h-[92%]">
            {mapEdges.map((e, i) => {
              const a = nodeById(e.from); const b = nodeById(e.to);
              if (!a || !b) return null;
              const essEdge = e.from === 'ess';
              return (
                <g key={i}>
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={essEdge && drActive ? '#F97316' : '#334155'} strokeWidth={essEdge && drActive ? 0.8 : 0.5} />
                  <circle r="0.9" fill={essEdge ? '#F97316' : '#3B82F6'} opacity={essEdge && !drActive ? 0 : 0.9}>
                    <animateMotion dur={essEdge ? '1.2s' : '2.5s'} repeatCount="indefinite"
                      path={`M ${a.x} ${a.y} L ${b.x} ${b.y}`} />
                  </circle>
                </g>
              );
            })}
            {mapNodes.map((n) => (
              <g key={n.id}>
                <circle cx={n.x} cy={n.y} r={n.id === 'transformer' ? 4.5 : 3.5}
                  fill="#0F172A" stroke={NODE_COLOR[n.status] ?? '#34D399'} strokeWidth="0.8">
                  {n.id === 'ess' && drActive && (
                    <animate attributeName="r" values="3.5;4.5;3.5" dur="1s" repeatCount="indefinite" />
                  )}
                </circle>
                <text x={n.x} y={n.y + 7.5} textAnchor="middle" fontSize="2.8" fill="#94A3B8">{n.name}</text>
                <text x={n.x} y={n.y + 0.9} textAnchor="middle" fontSize="2.2" fill={NODE_COLOR[n.status] ?? '#34D399'}>
                  {n.id === 'ess' ? `${n.soc ?? 0}%` : n.id === 'grid-source' ? 'KEPCO' : `${Math.round(n.load_percent)}%`}
                </text>
              </g>
            ))}
          </svg>
        </div>

        {/* Right: units + control + ledger */}
        <div className="col-span-12 lg:col-span-3 flex flex-col gap-3 min-h-0">
          <div className="rounded-xl border border-[#1E293B] bg-[#0A0F1A] p-3">
            <p className="text-xs font-semibold text-[#94A3B8] mb-2">
              ESS 유닛 상태 (20) {drActive && <span className="text-[#F97316]">— {activeUnits}기 방전 중</span>}
            </p>
            <div className="grid grid-cols-10 gap-1.5">
              {Array.from({ length: 20 }).map((_, i) => (
                <div key={i} title={`유닛 ${i + 1}`}
                  className={`aspect-square rounded-sm transition-colors duration-500 ${
                    drActive && i < activeUnits ? 'bg-[#F97316] animate-pulse' : 'bg-[#34D399]/70'
                  }`} />
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-[#1E293B] bg-[#0A0F1A] p-3">
            <p className="text-xs font-semibold text-[#94A3B8] mb-2">긴급 관제</p>
            <div className="grid grid-cols-2 gap-2">
              <button disabled={busy}
                onClick={() => act(() => vppApi.issueDrEvent('SIMPLE', 3), 'SIMPLE 3 긴급 발령')}
                className="rounded-lg bg-[#EF4444] px-2 py-2 text-xs font-bold text-white hover:bg-[#DC2626] disabled:opacity-40">
                SIMPLE 3 발령
              </button>
              <button disabled={busy}
                onClick={() => act(() => vppApi.issueDrEvent('SIMPLE', 0), '이벤트 해제')}
                className="rounded-lg border border-[#334155] px-2 py-2 text-xs font-semibold text-[#94A3B8] hover:bg-[#1E293B] disabled:opacity-40">
                해제
              </button>
              <button disabled={busy}
                onClick={() => act(() => vppApi.triggerScenario('peak_discharge'), '피크 방전 시연')}
                className="rounded-lg border border-[#F97316]/50 px-2 py-2 text-xs font-semibold text-[#F97316] hover:bg-[#F97316]/10 disabled:opacity-40">
                ⚡ 피크 시연
              </button>
              <button disabled={busy}
                onClick={() => act(() => vppApi.triggerScenario('midnight_charge'), '심야 충전 시연')}
                className="rounded-lg border border-[#3B82F6]/50 px-2 py-2 text-xs font-semibold text-[#3B82F6] hover:bg-[#3B82F6]/10 disabled:opacity-40">
                🌙 충전 시연
              </button>
            </div>
            {banner && <p className="mt-2 text-xs text-[#F1F5F9]">{banner}</p>}
          </div>

          <div className="flex-1 rounded-xl border border-[#1E293B] bg-[#0A0F1A] p-3 min-h-[120px] overflow-hidden">
            <p className="text-xs font-semibold text-[#94A3B8] mb-2">거래 장부</p>
            <div className="space-y-1.5 overflow-y-auto max-h-full pr-1">
              {ledger.length === 0 && <p className="text-xs text-[#475569]">거래 기록 없음 — DR 발령 시 자동 정산</p>}
              {ledger.map((e) => (
                <div key={e.id} className="flex items-center justify-between text-xs border-b border-[#1E293B]/60 pb-1">
                  <div className="min-w-0">
                    <span className={`mr-1.5 font-semibold ${e.type === 'DR정산' ? 'text-[#F97316]' : 'text-[#3B82F6]'}`}>
                      [{e.type}]
                    </span>
                    <span className="text-[#94A3B8]">{e.kwh}kWh</span>
                  </div>
                  <span className={`font-mono tabular-nums shrink-0 ml-2 ${e.revenue >= 0 ? 'text-[#34D399]' : 'text-[#94A3B8]'}`}>
                    {e.revenue >= 0 ? '+' : ''}₩{Math.round(e.revenue).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Ticker */}
      <footer className="border-t border-[#1E293B] bg-[#0A0F1A] overflow-hidden shrink-0">
        <div className="flex whitespace-nowrap py-1.5 animate-ticker">
          {(tickerItems.length ? tickerItems : ['시스템 정상 가동 중 — PeakBridge VPP 관제센터']).map((t, i) => (
            <span key={i} className="mx-8 text-xs text-[#64748B]">◆ {t}</span>
          ))}
        </div>
      </footer>
    </div>
  );
}
