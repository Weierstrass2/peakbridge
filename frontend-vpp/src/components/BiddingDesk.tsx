import { useEffect, useState } from 'react';
import BidChart from './BidChart';
import { consoleApi, type Bid, type MarketSession } from '../lib/api';

const fmtW = (n: number) => Math.round(n).toLocaleString('ko-KR');

function countdown(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

const STATUS_LABEL: Record<string, { t: string; c: string }> = {
  draft: { t: '작성 중', c: 'var(--tx-2)' },
  submitted: { t: '제출 완료 — 개찰 대기', c: 'var(--acc)' },
  cleared: { t: '개찰 완료', c: 'var(--ok)' },
};

export default function BiddingDesk({
  onLog,
}: {
  onLog: (lv: 'info' | 'ok' | 'warn' | 'crit', msg: string) => void;
}) {
  const [session, setSession] = useState<MarketSession | null>(null);
  const [bids, setBids] = useState<Bid[]>([]);
  const [mcpRef, setMcpRef] = useState<number[]>([]);
  const [secLeft, setSecLeft] = useState(0);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [history, setHistory] = useState<MarketSession[]>([]);

  const load = async () => {
    try {
      const { data } = await consoleApi.marketSession();
      setSession(data);
      setBids(data.bids);
      setSecLeft(data.seconds_to_deadline);
    } catch { /* noop */ }
    try {
      const { data } = await consoleApi.marketMcpForecast();
      setMcpRef(data.curve);
    } catch { /* noop */ }
    try {
      const { data } = await consoleApi.marketHistory();
      setHistory(data.sessions);
    } catch { /* noop */ }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => {
    const t = setInterval(() => setSecLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, []);

  const edit = (hour: number, field: 'qty_kw' | 'price', value: number) => {
    setBids((prev) => prev.map((b) => (b.hour === hour ? { ...b, [field]: value } : b)));
    setDirty(true);
  };

  const fillPeak = () => {
    // 참고 전략: MCP 예상 상위 8개 시간대에 100kW, 예상가의 92% 입찰
    const ranked = mcpRef.map((p, h) => ({ h, p })).sort((a, b) => b.p - a.p).slice(0, 8);
    const hours = new Set(ranked.map((r) => r.h));
    setBids((prev) =>
      prev.map((b) =>
        hours.has(b.hour)
          ? { ...b, qty_kw: 100, price: Math.round(mcpRef[b.hour] * 0.92 * 10) / 10 }
          : { ...b, qty_kw: 0, price: 0 },
      ),
    );
    setDirty(true);
    onLog('info', '전략 채움 — 피크 8개 시간대 100kW, 예상 MCP의 92%');
  };

  const act = async (fn: () => Promise<{ data?: unknown } | unknown>, label: string, lv: 'ok' | 'crit' = 'ok') => {
    setBusy(true);
    try {
      await fn();
      await load();
      setDirty(false);
      onLog(lv, label);
    } catch {
      onLog('warn', `${label} 실패`);
    } finally {
      setBusy(false);
    }
  };

  const st = STATUS_LABEL[session?.status ?? 'draft'] ?? STATUS_LABEL.draft;
  const results = session?.results ?? null;
  const resultByHour: Record<number, { awarded: boolean; mcp: number; expected_revenue: number }> = {};
  results?.hours.forEach((r) => { resultByHour[r.hour] = r; });
  const totalQty = bids.reduce((a, b) => a + b.qty_kw, 0);

  return (
    <div className="bidding">
      <div className="bid-head">
        <div className="bid-meta">
          <span>공급일 <b>{session?.delivery_date ?? '—'}</b></span>
          <span>상태 <b style={{ color: st.c }}>{st.t}</b></span>
          <span>입찰 물량 <b>{fmtW(totalQty)} kWh</b></span>
          {results && (
            <span>낙찰 <b style={{ color: 'var(--ok)' }}>
              {results.awarded_hours}구간 · ₩{fmtW(results.total_expected_revenue)}
            </b></span>
          )}
        </div>
        <div className="bid-deadline">
          입찰 마감 <b>{countdown(secLeft)}</b>
        </div>
      </div>

      <div className="bid-actions">
        <button className="cbtn wide" disabled={busy} onClick={fillPeak}>
          <b>전략 채움</b><span>피크 8구간</span>
        </button>
        <button
          className="cbtn wide" disabled={busy || !dirty}
          onClick={() => act(() => consoleApi.marketSaveBids(bids), '입찰서 저장')}
        >
          <b>저장</b><span>draft</span>
        </button>
        <button
          className="cbtn wide" disabled={busy || session?.status !== 'draft'}
          onClick={() => act(() => consoleApi.marketSubmit(), '입찰서 제출 — KPX DAM')}
        >
          <b>제출</b><span>submit</span>
        </button>
        <button
          className="cbtn wide crit" disabled={busy || session?.status !== 'submitted'}
          onClick={() => act(() => consoleApi.marketClear(), '개찰 실행 — 낙찰 판정', 'crit')}
        >
          <b>개찰</b><span>clearing</span>
        </button>
      </div>

      <div className="bid-cols">
      <div className="bid-left">
        <div className="bid-stepper">
          {['작성', '제출', '개찰', '급전'].map((s, i) => {
            const stage = session?.status === 'cleared' ? 2 : session?.status === 'submitted' ? 1 : 0;
            return (
              <span key={s} className={`step ${i <= stage ? 'on' : ''}`}>
                {i + 1} {s}{i < 3 && <i>—</i>}
              </span>
            );
          })}
          <span className="price-src">
            {session?.price_source?.engine === 'historical'
              ? `가격엔진: ${session.price_source.dataset} · ${session.price_source.replay_year}년 재생`
              : '가격엔진: 형상 모델'}
          </span>
        </div>
        <BidChart mcp={mcpRef} bids={bids} results={results?.hours ?? null} />
        <div className="bidchart-legend">
          <span className="key"><i style={{ background: '#E8A33D' }} />예상 MCP</span>
          <span className="key"><i style={{ background: '#4C8DFF' }} />내 입찰가</span>
          <span className="key"><i style={{ background: 'rgba(46,189,133,0.6)' }} />낙찰</span>
        </div>
      <div className="bid-scroll">
        <table className="dg bid-table">
          <thead>
            <tr>
              <th>구간</th>
              <th className="num">예상 MCP</th>
              <th className="num">물량 kW</th>
              <th className="num">입찰가 ₩</th>
              <th>판정</th>
              <th className="num">예상수익</th>
            </tr>
          </thead>
          <tbody>
            {bids.map((b) => {
              const r = resultByHour[b.hour];
              return (
                <tr key={b.hour} className={r?.awarded ? 'row-award' : ''}>
                  <td className="num" style={{ textAlign: 'left', color: 'var(--tx-3)' }}>
                    {String(b.hour).padStart(2, '0')}:00
                  </td>
                  <td className="num" style={{ color: 'var(--warn)' }}>
                    {mcpRef[b.hour] !== undefined ? mcpRef[b.hour].toFixed(1) : '—'}
                  </td>
                  <td className="num">
                    <input
                      className="cell-in" type="number" min={0} max={500} step={10}
                      value={b.qty_kw} disabled={session?.status === 'cleared'}
                      onChange={(e) => edit(b.hour, 'qty_kw', Number(e.target.value))}
                    />
                  </td>
                  <td className="num">
                    <input
                      className="cell-in" type="number" min={0} max={500} step={1}
                      value={b.price} disabled={session?.status === 'cleared'}
                      onChange={(e) => edit(b.hour, 'price', Number(e.target.value))}
                    />
                  </td>
                  <td>
                    {r ? (
                      <span className={`award ${r.awarded ? 'ok' : 'no'}`}>
                        {r.awarded ? '낙찰' : b.qty_kw > 0 ? '유찰' : '—'}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="num" style={{ color: r?.awarded ? 'var(--ok)' : 'var(--tx-3)' }}>
                    {r?.awarded ? `+₩${fmtW(r.expected_revenue)}` : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      </div>

      <aside className="bid-right">
        <div className="dr-cap">세션 이력</div>
        <div className="hist-scroll">
          {history.length === 0 && <div className="ledger-empty">이력 없음</div>}
          {history.map((h) => (
            <div key={h.session_id} className="hist-row">
              <div className="hist-top">
                <span className="hist-id">{h.session_id}</span>
                <span className="hist-date">{h.delivery_date}</span>
              </div>
              <div className="hist-bot">
                <span>낙찰 <b>{h.results?.awarded_hours ?? 0}구간</b></span>
                <span>물량 <b>{h.results?.total_award_kwh ?? 0}kWh</b></span>
                <span style={{ color: 'var(--ok)' }}>
                  ₩{Math.round((h.results?.total_expected_revenue ?? 0)).toLocaleString('ko-KR')}
                </span>
              </div>
            </div>
          ))}
        </div>
      </aside>
      </div>
    </div>
  );
}
