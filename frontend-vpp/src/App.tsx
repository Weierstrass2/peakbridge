import { useEffect, useRef, useState } from 'react';
import AssetsPanel from './components/AssetsPanel';
import DrPanel from './components/DrPanel';
import MapPanel from './components/MapPanel';
import MarketPanel from './components/MarketPanel';
import {
  consoleApi,
  type LedgerSummary,
  type Portfolio,
  type StreamSnapshot,
} from './lib/api';

/* ── 유틸 ─────────────────────────────────────────────── */

const fmt = (n: number, d = 1) =>
  n.toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d });

const fmtW = (n: number) => `${Math.round(n).toLocaleString('ko-KR')}`;

interface LogLine {
  ts: string;
  lv: 'info' | 'ok' | 'warn' | 'crit';
  msg: string;
}

const nowTs = () =>
  new Date().toLocaleTimeString('en-GB', { hour12: false });

/* ── 마켓바 ────────────────────────────────────────────── */

function MarketBar({
  snap, prevSmp, freq, flexKw, connected,
}: {
  snap: StreamSnapshot | null;
  prevSmp: number | null;
  freq: number;
  flexKw: number | null;
  connected: boolean;
}) {
  const [clock, setClock] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const smp = snap?.smp ?? null;
  const delta = smp !== null && prevSmp !== null ? smp - prevSmp : null;

  return (
    <div className="marketbar">
      <div className="brand">
        <b>PEAKBRIDGE</b>
        <span>VPP OS</span>
      </div>

      <div className="tick">
        <span className="k">SMP</span>
        <span className="v">
          {smp !== null ? fmt(smp) : '—'}<small>₩/kWh</small>
          {delta !== null && Math.abs(delta) >= 0.05 && (
            <span className={`delta ${delta > 0 ? 'up' : 'down'}`}>
              {delta > 0 ? '▲' : '▼'} {fmt(Math.abs(delta))}
            </span>
          )}
        </span>
      </div>

      <div className="tick">
        <span className="k">VPP 출력</span>
        <span className="v">{snap ? fmt(snap.total_output_kw) : '—'}<small>kW</small></span>
      </div>

      <div className="tick">
        <span className="k">가용 유연성</span>
        <span className="v">{flexKw !== null ? fmt(flexKw, 0) : '—'}<small>kW</small></span>
      </div>

      <div className="tick">
        <span className="k">수요</span>
        <span className="v">{snap ? fmt(snap.demand_kw, 0) : '—'}<small>kW</small></span>
      </div>

      <div className="tick">
        <span className="k">계통주파수</span>
        <span className="v">{fmt(freq, 2)}<small>Hz</small></span>
      </div>

      <div className="tick">
        <span className="k">DR 상태</span>
        <span className="v" style={{ color: snap?.dr_active ? 'var(--crit)' : 'var(--ok)', fontSize: 12 }}>
          {snap?.dr_active ? `대응 중 ${snap.discharge_percent}%` : '정상'}
        </span>
      </div>

      <div className="mb-right">
        <button
          className="fsbtn"
          title="전체화면 (F)"
          onClick={() => {
            if (document.fullscreenElement) document.exitFullscreen();
            else document.documentElement.requestFullscreen();
          }}
        >FULL</button>
        <div className="conn">
          <span className={`dot ${connected ? 'live' : 'err'}`} />
          {connected ? 'LIVE' : 'NO FEED'}
        </div>
        <span className="clock">
          {clock.toLocaleTimeString('en-GB', { hour12: false })}
          <small style={{ fontSize: 9, color: 'var(--tx-3)', marginLeft: 4 }}>KST</small>
        </span>
      </div>
    </div>
  );
}

/* ── 내비 레일 ─────────────────────────────────────────── */

const NAV = [
  { id: 'overview', label: '통합 개요', stage: null },
  { id: 'market', label: '시장·가격', stage: 'P2' },
  { id: 'assets', label: '자원 관제', stage: 'P3' },
  { id: 'drops', label: 'DR 운영', stage: 'P4' },
  { id: 'map', label: '전국 현황', stage: 'P5' },
  { id: 'settle', label: '정산 원장', stage: 'P4' },
];

function Rail() {
  return (
    <nav className="rail">
      <div className="rail-cap">CONSOLE</div>
      {NAV.map((n) => (
        <div key={n.id} className={`rail-item ${n.id === 'overview' ? 'active' : ''}`}>
          {n.label}
          {n.stage && <span className="stage">{n.stage}</span>}
        </div>
      ))}
      <div className="rail-sep" />
      <div className="rail-cap">SITE</div>
      <div className="rail-item">부산 — 실증단지 A</div>
    </nav>
  );
}

/* ── 패널 ──────────────────────────────────────────────── */

function Panel({
  title, sub, span, children,
}: {
  title: string; sub?: string; span: string; children: React.ReactNode;
}) {
  return (
    <section className="panel" style={{ gridColumn: span }}>
      <header className="panel-h">
        <span className="t">{title}</span>
        {sub && <span className="s">{sub}</span>}
      </header>
      <div className="panel-b">{children}</div>
    </section>
  );
}

/* ── 앱 ────────────────────────────────────────────────── */

export default function App() {
  const [snap, setSnap] = useState<StreamSnapshot | null>(null);
  const [prevSmp, setPrevSmp] = useState<number | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [ledger, setLedger] = useState<LedgerSummary | null>(null);
  const [connected, setConnected] = useState(false);
  const [latency, setLatency] = useState<number | null>(null);
  const [freq, setFreq] = useState(60.0);
  const [logs, setLogs] = useState<LogLine[]>([
    { ts: nowTs(), lv: 'info', msg: '콘솔 세션 시작 — 백엔드 피드 연결 시도' },
  ]);
  const lastSmp = useRef<number | null>(null);

  const pushLog = (lv: LogLine['lv'], msg: string) =>
    setLogs((prev) => [{ ts: nowTs(), lv, msg }, ...prev.slice(0, 60)]);

  // F키 전체화면
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === 'f' || e.key === 'F') && !(e.target instanceof HTMLInputElement)) {
        if (document.fullscreenElement) document.exitFullscreen();
        else document.documentElement.requestFullscreen();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // 3초 스트림
  useEffect(() => {
    let alive = true;
    let wasConnected: boolean | null = null;
    let wasDr = false;

    const tick = async () => {
      try {
        const { data, latencyMs } = await consoleApi.stream();
        if (!alive) return;
        setPrevSmp(lastSmp.current);
        lastSmp.current = data.smp;
        setSnap(data);
        setLatency(latencyMs);
        setConnected(true);
        setFreq(60 + (Math.random() - 0.5) * 0.04);
        if (wasConnected === false || wasConnected === null) pushLog('ok', `피드 연결됨 — ${latencyMs}ms`);
        if (data.dr_active && !wasDr) pushLog('crit', `DR 이벤트 활성 — 방전 지령 ${data.discharge_percent}%`);
        if (!data.dr_active && wasDr) pushLog('ok', 'DR 이벤트 종료 — 정상 운전 복귀');
        wasDr = data.dr_active;
        wasConnected = true;
      } catch {
        if (!alive) return;
        setConnected(false);
        if (wasConnected !== false) pushLog('warn', '피드 유실 — 재시도 중');
        wasConnected = false;
      }
    };
    tick();
    const t = setInterval(tick, 3000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  // 15초 포트폴리오/장부
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const { data } = await consoleApi.portfolio();
        if (alive) setPortfolio(data);
      } catch { /* noop */ }
      try {
        const { data } = await consoleApi.ledger();
        if (alive) setLedger(data.summary);
      } catch { /* noop */ }
    };
    tick();
    const t = setInterval(tick, 15_000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const liveA = portfolio?.buildings.find((b) => b.live);

  return (
    <div className="app">
      <MarketBar
        snap={snap}
        prevSmp={prevSmp}
        freq={freq}
        flexKw={portfolio?.available_flexibility_kw ?? null}
        connected={connected}
      />

      <div className="app-body">
        <Rail />

        <main className="main">
          <div className="grid">
            <Panel title="포트폴리오 요약" sub={`${portfolio?.building_count ?? '—'} SITES`} span="span 3">
              <div className="stat-rows">
                <div className="stat-row">
                  <span className="k">총 ESS 용량</span>
                  <span className="v">{portfolio ? fmt(portfolio.total_capacity_kwh, 0) : '—'}<small>kWh</small></span>
                </div>
                <div className="stat-row">
                  <span className="k">가용 유연성</span>
                  <span className="v" style={{ color: 'var(--acc)' }}>
                    {portfolio ? fmt(portfolio.available_flexibility_kw, 0) : '—'}<small>kW</small>
                  </span>
                </div>
                <div className="stat-row">
                  <span className="k">실증단지 A SOC</span>
                  <span className="v" style={{ color: (liveA?.current_soc ?? 100) < 30 ? 'var(--warn)' : 'var(--ok)' }}>
                    {liveA ? fmt(liveA.current_soc, 0) : '—'}<small>%</small>
                  </span>
                </div>
                <div className="stat-row">
                  <span className="k">금일 정산 수익</span>
                  <span className="v" style={{ color: 'var(--ok)' }}>
                    {ledger ? `₩${fmtW(ledger.today_revenue)}` : '—'}
                  </span>
                </div>
              </div>
            </Panel>

            <Panel title="시장 — SMP · 수요 실시간" sub="3s FEED / KST" span="span 6">
              <MarketPanel snap={snap} />
            </Panel>

            <Panel title="시스템 로그" sub="LIVE" span="span 3">
              <div className="log">
                {logs.map((l, i) => (
                  <div key={i} className="log-line">
                    <span className="ts">{l.ts}</span>
                    <span className={`lv ${l.lv}`}>{l.lv.toUpperCase()}</span>
                    <span>{l.msg}</span>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="자원 관제 — 사이트·유닛·계통" sub="20 UNITS / 3 SITES" span="span 6">
              <AssetsPanel portfolio={portfolio} snap={snap} />
            </Panel>

            <Panel title="DR 운영 콘솔" sub="OpenADR 2.0b" span="span 3">
              <DrPanel onLog={pushLog} />
            </Panel>

            <Panel title="전국 현황" sub="3 SITES" span="span 3">
              <MapPanel portfolio={portfolio} snap={snap} />
            </Panel>
          </div>

          <footer className="statusbar">
            <span>ENV <b>production</b></span>
            <span>API <b>{consoleApi.base.replace('https://', '')}</b></span>
            <span>POLL <b>3s</b></span>
            <div className="sb-right">
              <span>LATENCY <b>{latency !== null ? `${latency}ms` : '—'}</b></span>
              <span>FEED <b style={{ color: connected ? 'var(--ok)' : 'var(--crit)' }}>{connected ? 'CONNECTED' : 'DOWN'}</b></span>
            </div>
          </footer>
        </main>
      </div>
    </div>
  );
}
