import { useCallback, useEffect, useState } from 'react';
import {
  consoleApi,
  type DeskOverview,
  type DeskPnl,
  type DeskTca,
  type Fill,
  type ForecastQuality,
  type HedgePlan,
  type OverfitReport,
  type PreTrade,
  type SettlementCheck,
  type StochasticPlan,
} from '../lib/api';

const won = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : Math.round(n).toLocaleString('ko-KR');

const signed = (n: number) => (n > 0 ? `+${won(n)}` : won(n));
const sevColor = (s: string) =>
  s === 'breach' ? 'var(--crit)' : s === 'warn' ? 'var(--warn)' : 'var(--ok)';

/** 트레이딩 데스크 — 리스크·손익분해·블로터·체결품질을 한 화면에.
 *
 *  실제 데스크의 하루 흐름을 그대로 배치했다:
 *  사전 리스크 심사 → 스트레스 → (제출·개찰) → 손익 분해 → 체결 품질 리뷰 */
export default function TradingDesk({
  onLog,
}: {
  onLog: (lv: 'info' | 'ok' | 'warn' | 'crit', msg: string) => void;
}) {
  const [ov, setOv] = useState<DeskOverview | null>(null);
  const [pt, setPt] = useState<PreTrade | null>(null);
  const [pnl, setPnl] = useState<DeskPnl | null>(null);
  const [fills, setFills] = useState<Fill[]>([]);
  const [tca, setTca] = useState<DeskTca>({});
  const [fq, setFq] = useState<ForecastQuality>({});
  const [hedge, setHedge] = useState<HedgePlan | null>(null);
  const [stoch, setStoch] = useState<StochasticPlan | null>(null);
  const [availRatio, setAvailRatio] = useState(0.6);   // 급전 시점 가용 에너지 시나리오
  const [settle, setSettle] = useState<SettlementCheck | null>(null);
  const [errMode, setErrMode] = useState('underpay');
  const [ofit, setOfit] = useState<OverfitReport | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const safe = async <T,>(p: Promise<{ data: T }>, set: (v: T) => void) => {
      try { set((await p).data); } catch { /* 개별 실패는 화면을 깨뜨리지 않는다 */ }
    };
    await Promise.all([
      safe(consoleApi.deskOverview(), setOv),
      safe(consoleApi.deskPnl(), setPnl),
      safe(consoleApi.deskBlotter(40), (d) => setFills(d.fills)),
      safe(consoleApi.deskTca(), setTca),
      safe(consoleApi.deskForecastQuality(), setFq),
    ]);
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const runPreTrade = async () => {
    setBusy(true);
    try {
      const { data } = await consoleApi.deskPreTrade();
      setPt(data);
      onLog(
        data.blocked ? 'crit' : data.status === 'warn' ? 'warn' : 'ok',
        data.blocked
          ? `사전 리스크 심사 — 제출 차단: ${data.reason}`
          : `사전 리스크 심사 통과 (${data.strategy}) · VaR95 ₩${won(data.var95_won)}`,
      );
    } catch { onLog('warn', '사전 리스크 심사 실패'); }
    finally { setBusy(false); }
  };

  const runStochastic = async () => {
    setBusy(true);
    try {
      const { data } = await consoleApi.deskStochastic(200);
      setStoch(data);
      onLog(
        'ok',
        `확률적 입찰 — 시나리오 ${data.scenarios}개 · 기대 ₩${won(data.expected_won)} · ` +
          `CVaR5 ₩${won(data.cvar5_won)} · 손실확률 ${Math.round((data.loss_prob ?? 0) * 100)}%`,
      );
    } catch { onLog('warn', '확률적 입찰 계산 실패'); }
    finally { setBusy(false); }
  };

  const runHedge = async (ratio = availRatio) => {
    setBusy(true);
    try {
      const { data } = await consoleApi.deskHedge(ratio);
      setHedge(data);
      const sm = data.summary ?? {};
      onLog(
        (sm.hedged_kwh ?? 0) > 0 ? 'ok' : 'info',
        `RT 헤지 — 부족 ${sm.shortfall_kwh ?? 0}kWh 중 ${sm.hedged_kwh ?? 0}kWh 매수 커버 · ` +
          `위약 회피 ₩${won(sm.penalty_avoided_won)} · 커버리지 ${sm.coverage_after ?? '—'}`,
      );
    } catch { onLog('warn', 'RT 헤지 계획 실패'); }
    finally { setBusy(false); }
  };

  const runSettlement = async (mode = errMode) => {
    setBusy(true);
    try {
      const { data } = await consoleApi.deskSettlement(mode);
      setSettle(data);
      onLog(
        data.status === 'dispute' ? 'crit' : data.status === 'minor' ? 'warn' : 'ok',
        `정산 검증 — ${data.summary}` +
          ((data.underpaid_won ?? 0) > 0 ? ` · 미지급 ₩${won(data.underpaid_won)}` : ''),
      );
    } catch { onLog('warn', '정산 검증 실패'); }
    finally { setBusy(false); }
  };

  const runOverfit = async () => {
    setBusy(true);
    try {
      const { data } = await consoleApi.deskOverfit(60);
      setOfit(data);
      const d = data.deflated_sharpe ?? {};
      const p = data.pbo ?? {};
      onLog('ok', `과최적화 진단 — DSR ${d.deflated_sharpe_prob} (${d.verdict}) · PBO ${p.pbo} (${p.verdict})`);
    } catch { onLog('warn', '과최적화 진단 실패'); }
    finally { setBusy(false); }
  };

  const seed = async () => {
    setBusy(true);
    try {
      // post()는 data 래핑 없이 본문을 그대로 돌려준다
      const r = await consoleApi.deskSeed('zscore', 30);
      onLog('ok', `데스크 시딩 — 과거 ${r.seeded}일 · 체결 ${r.fills}건 적재`);
      await load();
    } catch { onLog('warn', '시딩 실패'); }
    finally { setBusy(false); }
  };

  const totals = pnl?.totals ?? {};
  const roll = pnl?.rolling;
  const points = roll?.points ?? [];
  const maxEq = Math.max(1, ...points.map((p) => Math.abs(p.equity)));

  // 손익 분해 막대 스케일
  const attrRows: [string, number, string][] = [
    ['기준 매출', totals.base_revenue ?? 0, 'var(--acc)'],
    ['가격 효과', totals.price_effect ?? 0, 'var(--vio)'],
    ['용량요금', totals.capacity_payment ?? 0, 'var(--ok)'],
    ['열화비용', totals.degradation ?? 0, 'var(--tx-3)'],
    ['위약금', totals.penalty ?? 0, 'var(--crit)'],
  ];
  const attrMax = Math.max(1, ...attrRows.map(([, v]) => Math.abs(v)));

  return (
    <div className="desk">
      {/* ── 헤더 KPI ── */}
      <div className="desk-kpis">
        {[
          ['누적 손익', signed(ov?.equity_won ?? 0), (ov?.equity_won ?? 0) >= 0 ? 'var(--ok)' : 'var(--crit)'],
          ['롤링 Sharpe', ov?.current_sharpe ?? '—', 'var(--tx-1)'],
          ['현재 드로다운', won(ov?.current_drawdown_won ?? 0), 'var(--warn)'],
          ['VaR 95%', won(ov?.var95_won ?? 0), 'var(--crit)'],
          ['CVaR 95%', won(ov?.cvar95_won ?? 0), 'var(--crit)'],
          ['세션', `${ov?.sessions ?? 0}일`, 'var(--tx-2)'],
          ['전략', ov?.active_strategy ?? '—', 'var(--acc)'],
        ].map(([k, v, c]) => (
          <div className="desk-kpi" key={String(k)}>
            <span className="k">{k}</span>
            <b style={{ color: String(c) }}>{v}</b>
          </div>
        ))}
        <div className="desk-actions">
          <button className="cbtn tiny" disabled={busy} onClick={runPreTrade} type="button">
            <b>사전 리스크 심사</b>
          </button>
          <button className="cbtn tiny" disabled={busy} onClick={runStochastic} type="button">
            <b>확률적 입찰</b>
          </button>
          <button className="cbtn tiny" disabled={busy} onClick={() => runHedge()} type="button">
            <b>RT 헤지 계획</b>
          </button>
          <button className="cbtn tiny" disabled={busy} onClick={() => runSettlement()} type="button">
            <b>정산 검증</b>
          </button>
          <button className="cbtn tiny" disabled={busy} onClick={runOverfit} type="button">
            <b>과최적화 진단</b>
          </button>
          <button className="cbtn tiny" disabled={busy} onClick={seed} type="button">
            <b>과거 30일 적재</b>
          </button>
        </div>
      </div>

      {ov?.kill_switch && (
        <div className="desk-kill">
          거래 중지 (킬스위치) — {ov.reason}
          <button
            className="cbtn tiny"
            onClick={async () => { await consoleApi.deskKillReset(); onLog('warn', '킬스위치 해제 — 거래 재개'); load(); }}
            type="button"
          >
            <b>해제</b>
          </button>
        </div>
      )}

      <div className="desk-grid">
        {/* ── 사전 리스크 심사 ── */}
        <section className="desk-card">
          <h4>사전 리스크 심사 <span>PRE-TRADE</span></h4>
          {!pt ? (
            <div className="desk-empty">[사전 리스크 심사]를 눌러 현재 전략의 입찰안을 검사합니다.</div>
          ) : (
            <>
              <div className="desk-verdict" style={{ color: sevColor(pt.status) }}>
                {pt.blocked ? `제출 차단 — ${pt.reason}` : pt.status === 'warn' ? '경고 있음 — 제출 가능' : '전 한도 통과'}
              </div>
              <table className="dg">
                <thead>
                  <tr><th>한도</th><th className="num">현재</th><th className="num">한도값</th><th className="num">소진율</th></tr>
                </thead>
                <tbody>
                  {pt.checks.map((c) => {
                    const ratio = c.limit > 0 ? Math.min(1.5, c.value / c.limit) : 0;
                    return (
                      <tr key={c.code}>
                        <td style={{ color: sevColor(c.severity) }}>{c.message}</td>
                        <td className="num">{won(c.value)}</td>
                        <td className="num" style={{ color: 'var(--tx-3)' }}>{won(c.limit)}</td>
                        <td className="num">
                          <div className="lim-bar">
                            <i style={{ width: `${Math.min(100, ratio * 100)}%`, background: sevColor(c.severity) }} />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </section>

        {/* ── 스트레스 시나리오 ── */}
        <section className="desk-card">
          <h4>스트레스 시나리오 <span>STRESS</span></h4>
          {!pt ? (
            <div className="desk-empty">사전 심사를 실행하면 충격별 손익이 계산됩니다.</div>
          ) : (
            <table className="dg">
              <thead>
                <tr><th>시나리오</th><th>설명</th><th className="num">손익 ₩</th><th className="num">기준 대비</th></tr>
              </thead>
              <tbody>
                {pt.stress.map((s) => (
                  <tr key={s.scenario}>
                    <td><b>{s.scenario}</b></td>
                    <td style={{ color: 'var(--tx-3)', fontSize: 10 }}>{s.description}</td>
                    <td className="num" style={{ color: s.pnl_won >= 0 ? 'var(--ok)' : 'var(--crit)' }}>{won(s.pnl_won)}</td>
                    <td className="num" style={{ color: s.delta_won < 0 ? 'var(--crit)' : 'var(--tx-2)' }}>
                      {s.delta_won === 0 ? '—' : signed(s.delta_won)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* ── 손익 분해 ── */}
        <section className="desk-card">
          <h4>손익 분해 <span>P&amp;L ATTRIBUTION</span></h4>
          <div className="attr">
            {attrRows.map(([label, v, c]) => (
              <div className="attr-row" key={label}>
                <span className="lb">{label}</span>
                <div className="track">
                  <i style={{ width: `${(Math.abs(v) / attrMax) * 100}%`, background: c }} />
                </div>
                <span className="vl" style={{ color: v < 0 ? 'var(--crit)' : 'var(--tx-1)' }}>{signed(v)}</span>
              </div>
            ))}
            <div className="attr-row total">
              <span className="lb">순손익</span>
              <div className="track" />
              <span className="vl" style={{ color: (totals.net ?? 0) >= 0 ? 'var(--ok)' : 'var(--crit)' }}>
                {signed(totals.net ?? 0)}
              </span>
            </div>
          </div>
          <div className="desk-note">
            기준 매출 = 예측대로 실현됐을 매출 · 가격 효과 = 실제 가격이 예측과 달라 생긴 차이
          </div>
        </section>

        {/* ── 누적 손익 곡선 ── */}
        <section className="desk-card">
          <h4>누적 손익 · 드로다운 <span>EQUITY CURVE</span></h4>
          {points.length === 0 ? (
            <div className="desk-empty">세션 기록이 없습니다. [과거 30일 적재]로 채울 수 있습니다.</div>
          ) : (
            <>
              <svg className="eq" viewBox={`0 0 ${Math.max(points.length, 2)} 100`} preserveAspectRatio="none">
                <polyline
                  fill="none" stroke="var(--ok)" strokeWidth="1.2" vectorEffect="non-scaling-stroke"
                  points={points.map((p, i) => `${i},${100 - (p.equity / maxEq) * 90}`).join(' ')}
                />
                <polyline
                  fill="none" stroke="var(--crit)" strokeWidth="1" strokeDasharray="3 2" vectorEffect="non-scaling-stroke"
                  points={points.map((p, i) => `${i},${100 - (Math.abs(p.drawdown) / maxEq) * 90}`).join(' ')}
                />
              </svg>
              <div className="eq-legend">
                <span><i style={{ background: 'var(--ok)' }} />누적 손익 ₩{won(roll?.equity_won)}</span>
                <span><i style={{ background: 'var(--crit)' }} />최대 낙폭 ₩{won(roll?.max_drawdown)}</span>
              </div>
            </>
          )}
        </section>

        {/* ── 체결품질 · 예측품질 ── */}
        <section className="desk-card">
          <h4>체결 품질 · 예측 품질 <span>TCA / FORECAST</span></h4>
          <div className="kv-grid">
            <div><span>평균 슬리피지</span><b>₩{tca.avg_slippage ?? '—'}</b></div>
            <div><span>낙찰률</span><b>{tca.hit_ratio !== undefined ? `${Math.round((tca.hit_ratio ?? 0) * 100)}%` : '—'}</b></div>
            <div><span>확보 매출</span><b>₩{won(tca.captured_won)}</b></div>
            <div><span>기회손실</span><b style={{ color: 'var(--warn)' }}>₩{won(tca.missed_value_won)}</b></div>
            <div><span>예측 MAPE</span><b>{fq.mape_pct ?? '—'}%</b></div>
            <div><span>예측 편향</span><b>{fq.bias ?? '—'}</b></div>
            <div><span>Pinball loss</span><b>{fq.pinball_loss ?? '—'}</b></div>
            <div><span>표본</span><b>{fq.samples ?? 0}</b></div>
          </div>
          {fq.verdict && <div className="desk-note">예측 진단: {fq.verdict}</div>}
        </section>


        {/* ── 확률적 입찰 (시나리오 분포) ── */}
        <section className="desk-card">
          <h4>확률적 입찰 <span>SCENARIO · CVaR</span></h4>
          {!stoch ? (
            <div className="desk-empty">[확률적 입찰]을 누르면 가격·가용에너지 시나리오 200개로 분포를 계산합니다.</div>
          ) : (
            <>
              <div className="dist">
                {(() => {
                  // 5구간 요약 분포 — 최악 / VaR / 기대 / 상위 / 최고
                  const marks: [string, number, string][] = [
                    ['최악', stoch.worst_won ?? 0, 'var(--crit)'],
                    ['CVaR 5%', stoch.cvar5_won ?? 0, 'var(--crit)'],
                    ['VaR 5%', stoch.var5_won ?? 0, 'var(--warn)'],
                    ['기대', stoch.expected_won ?? 0, 'var(--ok)'],
                    ['최고', stoch.best_won ?? 0, 'var(--acc)'],
                  ];
                  const lo = Math.min(...marks.map((m) => m[1]), 0);
                  const hi = Math.max(...marks.map((m) => m[1]), 1);
                  const span = hi - lo || 1;
                  const zero = ((0 - lo) / span) * 100;
                  return marks.map(([label, v, c]) => {
                    const x = ((v - lo) / span) * 100;
                    const left = Math.min(x, zero);
                    const width = Math.abs(x - zero);
                    return (
                      <div className="dist-row" key={label}>
                        <span className="lb">{label}</span>
                        <div className="track">
                          <i className="zero" style={{ left: `${zero}%` }} />
                          <b style={{ left: `${left}%`, width: `${Math.max(width, 0.8)}%`, background: c }} />
                        </div>
                        <span className="vl" style={{ color: v < 0 ? 'var(--crit)' : 'var(--tx-1)' }}>{signed(v)}</span>
                      </div>
                    );
                  });
                })()}
              </div>
              <div className="kv-grid" style={{ marginTop: 8, gridTemplateColumns: 'repeat(3, 1fr)' }}>
                <div><span>손실 확률</span><b style={{ color: (stoch.loss_prob ?? 0) > 0.2 ? 'var(--warn)' : 'var(--ok)' }}>
                  {Math.round((stoch.loss_prob ?? 0) * 100)}%
                </b></div>
                <div><span>응찰 구간</span><b>{stoch.active_hours ?? 0}</b></div>
                <div><span>시나리오</span><b>{stoch.scenarios ?? 0}</b></div>
              </div>
              <div className="desk-note">
                기대이익만 보지 않고 하위 5% 꼬리(CVaR)가 허용선 아래로 내려가지 않도록 제약을 건 해입니다.
              </div>
            </>
          )}
        </section>

        {/* ── 실시간시장 헤지 ── */}
        <section className="desk-card">
          <h4>실시간시장 헤지 <span>RT HEDGE</span></h4>
          <div className="hedge-ctl">
            <span>급전 시점 가용 에너지</span>
            <input
              type="range" min={0.2} max={1} step={0.1} value={availRatio}
              onChange={(e) => setAvailRatio(Number(e.target.value))}
              onMouseUp={() => runHedge()}
            />
            <b>{Math.round(availRatio * 100)}%</b>
          </div>
          {!hedge || (hedge.decisions ?? []).length === 0 ? (
            <div className="desk-empty">[RT 헤지 계획]을 누르면 부족 구간별로 매수 커버 여부를 판단합니다.</div>
          ) : (
            <>
              <div className="hedge-sum">
                <div><span>인도 의무</span><b>{hedge.summary.obligation_kwh ?? 0} kWh</b></div>
                <div><span>부족분</span><b style={{ color: 'var(--warn)' }}>{hedge.summary.shortfall_kwh ?? 0} kWh</b></div>
                <div><span>RT 매수</span><b style={{ color: 'var(--acc)' }}>{hedge.summary.hedged_kwh ?? 0} kWh</b></div>
                <div><span>위약 회피</span><b style={{ color: 'var(--ok)' }}>₩{won(hedge.summary.penalty_avoided_won)}</b></div>
                <div><span>커버리지</span><b>{hedge.summary.coverage_after ?? '—'}</b></div>
              </div>
              <table className="dg">
                <thead>
                  <tr><th className="num">구간</th><th className="num">부족 kW</th><th className="num">RT가</th>
                    <th className="num">위약단가</th><th>판단</th></tr>
                </thead>
                <tbody>
                  {hedge.decisions.filter((d) => d.shortfall_kw > 0).map((d) => (
                    <tr key={d.hour}>
                      <td className="num">{String(d.hour).padStart(2, '0')}시</td>
                      <td className="num" style={{ color: 'var(--warn)' }}>{d.shortfall_kw}</td>
                      <td className="num">{d.rt_price}</td>
                      <td className="num" style={{ color: 'var(--crit)' }}>{d.penalty_price}</td>
                      <td style={{ color: d.action === 'hedge' ? 'var(--ok)' : 'var(--crit)' }}>
                        {d.action === 'hedge' ? 'RT 매수 커버' : '위약금 수용'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {hedge.comparison && (
                <div className="hedge-cmp">
                  헤지 없음 <b style={{ color: 'var(--crit)' }}>{signed(hedge.comparison.without_hedge_won)}</b>
                  <span>→</span>
                  헤지 적용 <b style={{ color: 'var(--ok)' }}>{signed(hedge.comparison.with_hedge_won)}</b>
                  <em>개선 {signed(hedge.comparison.improvement_won)}</em>
                </div>
              )}
              <div className="desk-note">
                무조건 헤지하지 않습니다. RT 매수비용이 위약금(MCP×1.2)보다 쌀 때만 커버합니다.
              </div>
            </>
          )}
        </section>


        {/* ── 정산 검증 ── */}
        <section className="desk-card">
          <h4>정산 검증 <span>SHADOW SETTLEMENT</span></h4>
          <div className="hedge-ctl">
            <span>정산서 오류 시나리오</span>
            <select
              value={errMode}
              onChange={(e) => { setErrMode(e.target.value); runSettlement(e.target.value); }}
              className="sel"
            >
              <option value="none">정상</option>
              <option value="underpay">에너지 정산금 누락</option>
              <option value="penalty_over">위약금 과다 부과</option>
              <option value="capacity_miss">용량요금 미지급</option>
            </select>
          </div>
          {!settle ? (
            <div className="desk-empty">[정산 검증]을 누르면 거래소 정산서와 자체 계산을 대조합니다.</div>
          ) : (
            <>
              <div
                className="desk-verdict"
                style={{ color: settle.status === 'dispute' ? 'var(--crit)' : settle.status === 'minor' ? 'var(--warn)' : 'var(--ok)' }}
              >
                {settle.summary}
              </div>
              <table className="dg">
                <thead>
                  <tr><th>항목</th><th className="num">자체 계산</th><th className="num">정산서</th>
                    <th className="num">차이</th><th className="num">%</th><th>판정</th></tr>
                </thead>
                <tbody>
                  {settle.checks.map((l) => (
                    <tr key={l.item}>
                      <td>{l.label}</td>
                      <td className="num">{won(l.ours_won)}</td>
                      <td className="num">{won(l.theirs_won)}</td>
                      <td className="num" style={{ color: l.diff_won < 0 ? 'var(--crit)' : l.diff_won > 0 ? 'var(--warn)' : 'var(--tx-3)' }}>
                        {l.diff_won === 0 ? '—' : signed(l.diff_won)}
                      </td>
                      <td className="num" style={{ color: 'var(--tx-3)' }}>{l.diff_pct}</td>
                      <td style={{ color: l.verdict === 'dispute' ? 'var(--crit)' : l.verdict === 'minor' ? 'var(--warn)' : 'var(--ok)' }}>
                        {l.verdict === 'dispute' ? '이의신청' : l.verdict === 'minor' ? '경미' : '일치'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="desk-note">
                허용오차(계량·반올림) 0.5% 이내는 일치로 봅니다. 2% 이상 어긋나면 소액이라도
                계통적 오류로 판단해 이의신청 대상으로 표시합니다.
              </div>
            </>
          )}
        </section>

        {/* ── 과최적화 진단 ── */}
        <section className="desk-card">
          <h4>과최적화 진단 <span>DSR · PBO</span></h4>
          {!ofit?.deflated_sharpe ? (
            <div className="desk-empty">[과최적화 진단]을 누르면 시행 횟수를 보정한 유의성을 계산합니다.</div>
          ) : (
            <>
              <div className="kv-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
                <div><span>관측 Sharpe</span><b>{ofit.deflated_sharpe.observed_sharpe_annual}</b></div>
                <div><span>우연 기대 최대</span><b style={{ color: 'var(--tx-3)' }}>{ofit.deflated_sharpe.expected_max_sharpe_annual}</b></div>
                <div><span>DSR</span><b style={{ color: ofit.deflated_sharpe.significant ? 'var(--ok)' : 'var(--warn)' }}>
                  {ofit.deflated_sharpe.deflated_sharpe_prob}
                </b></div>
                <div><span>PBO</span><b style={{ color: (ofit.pbo?.pbo ?? 0) < 0.25 ? 'var(--ok)' : 'var(--crit)' }}>
                  {ofit.pbo?.pbo}
                </b></div>
              </div>
              <div className="ofit-verdicts">
                <div>
                  <b>Deflated Sharpe</b>
                  <span>{ofit.deflated_sharpe.verdict}</span>
                  <em>전략 {ofit.deflated_sharpe.trials}개를 시험했다는 사실을 보정한 결과</em>
                </div>
                <div>
                  <b>PBO</b>
                  <span>{ofit.pbo?.verdict}</span>
                  <em>{ofit.pbo?.combinations}개 조합에서 학습 1등이 검증에서 중앙값 아래로 떨어진 비율</em>
                </div>
              </div>
              <div className="desk-note">
                최고 전략 <b>{ofit.best_strategy}</b> · 검증 {ofit.test_days}일 ·
                왜도 {ofit.deflated_sharpe.skew} / 첨도 {ofit.deflated_sharpe.kurtosis}
              </div>
            </>
          )}
        </section>

        {/* ── 블로터 ── */}
        <section className="desk-card wide">
          <h4>체결 블로터 <span>BLOTTER · {fills.length}건</span></h4>
          <div className="desk-scroll">
            <table className="dg">
              <thead>
                <tr>
                  <th>체결 ID</th><th>일자</th><th className="num">구간</th><th>전략</th>
                  <th className="num">물량 kW</th><th className="num">이행 kW</th>
                  <th className="num">입찰가</th><th className="num">체결가</th>
                  <th className="num">슬리피지</th><th className="num">금액 ₩</th><th>상태</th>
                </tr>
              </thead>
              <tbody>
                {fills.map((f) => (
                  <tr key={f.id}>
                    <td style={{ fontFamily: 'var(--font-num)' }}>{f.id}</td>
                    <td style={{ color: 'var(--tx-3)' }}>{f.date}</td>
                    <td className="num">{String(f.hour).padStart(2, '0')}시</td>
                    <td style={{ color: 'var(--acc)' }}>{f.strategy}</td>
                    <td className="num">{f.qty_kw}</td>
                    <td className="num">{f.delivered_kw}</td>
                    <td className="num">{f.bid_price}</td>
                    <td className="num">{f.clear_price}</td>
                    <td className="num" style={{ color: f.slippage < 3 ? 'var(--warn)' : 'var(--tx-2)' }}>
                      {f.slippage}
                    </td>
                    <td className="num">{won(f.value_won)}</td>
                    <td style={{ color: f.status === '이행' ? 'var(--ok)' : 'var(--warn)' }}>{f.status}</td>
                  </tr>
                ))}
                {fills.length === 0 && (
                  <tr><td colSpan={11} style={{ color: 'var(--tx-3)', textAlign: 'center', padding: 14 }}>
                    체결 없음 — [과거 30일 적재]로 시연 데이터를 채울 수 있습니다.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
