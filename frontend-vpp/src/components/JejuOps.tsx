import { useCallback, useEffect, useState } from 'react';
import {
  consoleApi,
  type JejuAssetCompare,
  type JejuCompare,
  type JejuOpsState,
  type JejuResult,
} from '../lib/api';

const won = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : Math.round(n).toLocaleString('ko-KR');
const pct = (n: number) => `${Math.round(n * 100)}%`;
const pos = (n: number) => (n >= 0 ? 'var(--ok)' : 'var(--crit)');

/** 제주 운영 시뮬레이터 — 플러스DR 발령에 실제로 대응해 보는 화면.
 *
 *  시연의 핵심 장면이다. 같은 요청, 같은 자원인데
 *  '어느 단지에 시키느냐'만으로 손익이 갈리는 것을 보여준다.
 *
 *  이행률은 두 방식 모두 높게 나온다. 차이는 계량기 피크에서 생긴다.
 *  성실하게 이행하는 것만으로는 부족하다는 것이 이 화면의 메시지다. */
export default function JejuOps({
  onLog,
}: {
  onLog: (lv: 'info' | 'ok' | 'warn' | 'crit', msg: string) => void;
}) {
  const [st, setSt] = useState<JejuOpsState | null>(null);
  const [cmp, setCmp] = useState<JejuCompare | null>(null);
  const [acmp, setAcmp] = useState<JejuAssetCompare | null>(null);
  const [res, setRes] = useState<JejuResult | null>(null);
  const [incentive, setIncentive] = useState(120);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setSt((await consoleApi.jejuOpsState()).data); } catch { /* 조용히 */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const fire = async () => {
    setBusy(true); setCmp(null); setAcmp(null); setRes(null);
    try {
      const data = await consoleApi.jejuOpsEvent();
      setSt(data);
      const e = data.event;
      onLog('warn',
        `플러스DR 발령 — ${e?.hour}시 · 요청 ${won(e?.request_kwh)}kWh · ` +
        `${e?.is_peak_hour ? '최대부하' : '경부하'} 시간대`);
    } catch { onLog('warn', '발령 실패'); }
    finally { setBusy(false); }
  };

  const runCompare = async () => {
    setBusy(true);
    try {
      const { data } = await consoleApi.jejuOpsCompare(incentive);
      setCmp(data);
      onLog(data.gap_won > 0 ? 'ok' : 'warn',
        `배분 방식 대조 — 격차 ₩${won(data.gap_won)} · ` +
        `균등 배분이 ${data.even.sites_over_peak}개 단지 피크를 올림`);
    } catch { onLog('warn', '대조 실패'); }
    finally { setBusy(false); }
  };

  const runAssetCompare = async () => {
    setBusy(true);
    try {
      const { data } = await consoleApi.jejuOpsAssetCompare(incentive);
      setAcmp(data);
      onLog('ok',
        `자산 방식 대조 — ESS 구매 회수 ${data.ess_owned.payback_years ?? '—'}년 vs ` +
        `EV 연계 그릇값 0원`);
    } catch { onLog('warn', '자산 대조 실패'); }
    finally { setBusy(false); }
  };

  const run = async (mode: 'peak' | 'even') => {
    setBusy(true);
    try {
      const data = await consoleApi.jejuOpsDispatch(mode, incentive);
      setRes(data);
      await load();
      onLog(data.net_won > 0 ? 'ok' : 'crit',
        `급전 완료 (${mode === 'peak' ? '피크 여유 기반' : '균등 배분'}) — ` +
        `이행 ${pct(data.delivery_rate)} · 순손익 ₩${won(data.net_won)}`);
    } catch { onLog('warn', '급전 실패'); }
    finally { setBusy(false); }
  };

  const step = async (fn: () => Promise<JejuOpsState>) => {
    setBusy(true); setCmp(null); setAcmp(null); setRes(null);
    try { setSt(await fn()); } catch { /* 조용히 */ }
    finally { setBusy(false); }
  };

  if (!st) return <div className="jops"><p className="prof-load">시뮬레이터 준비 중…</p></div>;

  const f = st.fleet;
  const ev = st.event;
  const maxLoad = Math.max(1, ...st.sites.map((s) => Math.max(s.contract_kw, s.month_peak_kw)));

  return (
    <div className="jops">
      {/* ── 조작 ── */}
      <div className="jo-bar">
        <button className="cbtn tiny" disabled={busy} onClick={fire} type="button">
          <b>플러스DR 발령</b>
        </button>
        <button className="cbtn tiny" disabled={busy || !ev} onClick={runCompare} type="button">
          <b>배분 방식 대조</b>
        </button>
        <button className="cbtn tiny" disabled={busy || !ev} onClick={runAssetCompare} type="button">
          <b>자산 방식 대조</b>
        </button>
        <button className="cbtn tiny" disabled={busy || !ev} onClick={() => run('peak')} type="button">
          <b>급전 — 피크 여유 기반</b>
        </button>
        <button className="cbtn tiny" disabled={busy || !ev} onClick={() => run('even')} type="button">
          급전 — 균등 배분
        </button>
        <button className="cbtn tiny" disabled={busy}
                onClick={() => step(consoleApi.jejuOpsAdvance)} type="button">
          1시간 진행
        </button>
        <button className="cbtn tiny" disabled={busy}
                onClick={() => step(() => consoleApi.jejuOpsReset(12))} type="button">
          초기화
        </button>
        <label className="jo-inc">
          정산단가 가정
          <input type="number" value={incentive} min={0} step={10} disabled={busy}
                 onChange={(e) => setIncentive(Number(e.target.value))} />
          ₩/kWh
        </label>
      </div>

      {/* ── 현재 상황 ── */}
      <div className="jo-kpis">
        {([
          ['참여 단지', `${f.online} / ${f.count}`, 'var(--tx-1)'],
          ['충전 여유', `${won(f.room_kwh)} kWh`, 'var(--tx-2)'],
          ['안전 충전 가능', `${won(f.safe_charge_kw)} kW`, 'var(--ok)'],
          ['평균 잔량', pct(f.avg_soc), 'var(--tx-2)'],
          ['시장 평균 이행률', pct(st.facts.market_delivery), 'var(--crit)'],
        ] as [string, string, string][]).map(([k, v, c]) => (
          <div className="desk-kpi" key={k}>
            <span className="k">{k}</span>
            <b style={{ color: c }}>{v}</b>
          </div>
        ))}
      </div>

      {/* ── 발령 배너 ── */}
      {ev ? (
        <div className={`jo-event ${ev.is_peak_hour ? 'hot' : ''}`}>
          <div className="je-l">
            <span className="k">플러스DR 발령</span>
            <b>{ev.hour}시 · 요청 {won(ev.request_kwh)} kWh</b>
          </div>
          <div className="je-m">
            <span>출력제어 {ev.curtail_mw} MW 동시 발생</span>
            <span>
              그 시각 요금 <b>₩{ev.tou_won}</b>
              {ev.is_peak_hour ? ' · 최대부하 시간대' : ' · 경부하 시간대'}
            </span>
          </div>
          {ev.is_peak_hour && (
            <div className="je-warn">
              충전하면 계량기 피크가 올라갑니다 — 여유 있는 단지만 골라야 합니다
            </div>
          )}
        </div>
      ) : (
        <div className="jo-idle">플러스DR 발령 버튼을 눌러 상황을 만들어 보세요</div>
      )}

      {/* ── 배분 방식 대조 (핵심) ── */}
      {cmp && (
        <div className="jo-sect">
          <div className="js-head">
            <b>같은 요청, 같은 자원 — 배분 방식만 다르게</b>
            <span className="js-sub">이행률이 아니라 계량기 피크에서 갈립니다</span>
          </div>
          <div className="jo-cmp">
            {([['even', '균등 배분', '여유를 보지 않고 모든 단지에'],
               ['peak', '피크 여유 기반 (PeakBridge)', '올려도 되는 단지만 골라서']] as const)
              .map(([key, title, desc]) => {
                const r = cmp[key];
                const win = key === 'peak';
                return (
                  <div className={`jc-col ${win ? 'win' : ''}`} key={key}>
                    <div className="jc-h">
                      <b>{title}</b>
                      <span>{desc}</span>
                    </div>
                    <div className="jc-net" style={{ color: pos(r.net_won) }}>
                      {won(r.net_won)}<small>원</small>
                    </div>
                    <div className="jc-rows">
                      {([
                        ['이행률', pct(r.delivery_rate), 'var(--tx-2)'],
                        ['인센티브', `+${won(r.incentive_won)}`, 'var(--ok)'],
                        ['전기 구입', `−${won(r.energy_cost_won)}`, 'var(--tx-3)'],
                        ['저장분 회수', `+${won(r.recovery_won)}`, 'var(--ok)'],
                        ['배터리 열화', `−${won(r.degradation_won)}`, 'var(--tx-3)'],
                        ['기본요금 상승', `−${won(r.peak_penalty_won)}`,
                          r.peak_penalty_won > 0 ? 'var(--crit)' : 'var(--tx-3)'],
                      ] as [string, string, string][]).map(([k, v, c]) => (
                        <div className="jc-r" key={k}>
                          <span>{k}</span>
                          <b className="num" style={{ color: c }}>{v}</b>
                        </div>
                      ))}
                    </div>
                    <div className={`jc-over ${r.sites_over_peak > 0 ? 'bad' : 'good'}`}>
                      피크 초과 단지 {r.sites_over_peak}곳
                    </div>
                  </div>
                );
              })}
          </div>
          <p className="jeju-verdict">{cmp.verdict}</p>
        </div>
      )}

      {acmp && !acmp.error && (
        <div className="jo-sect">
          <div className="js-head">
            <b>같은 흡수량, 다른 그릇 — 배터리를 살 것인가 빌릴 것인가</b>
            <span className="js-sub">
              버려지는 전기는 공짜지만 담을 배터리는 공짜가 아닙니다
            </span>
          </div>
          <div className="jo-cmp">
            {([['ess_owned', false], ['ev_fleet', true]] as const).map(([key, win]) => {
              const a = acmp[key];
              return (
                <div className={`jc-col ${win ? 'win' : ''}`} key={key}>
                  <div className="jc-h">
                    <b>{a.label}</b>
                    <span>{win ? '차주가 이미 산 배터리 · 할인이 대가'
                               : '우리가 사고 우리가 닳는다'}</span>
                  </div>
                  <div className="jc-net" style={{ color: a.capex_won > 0 ? 'var(--crit)' : 'var(--ok)' }}>
                    {won(a.capex_won)}<small>원 그릇값</small>
                  </div>
                  <div className="jc-rows">
                    {([
                      ['필요 배터리', a.need_capacity_kwh > 0
                        ? `${won(a.need_capacity_kwh)}kWh` : '없음',
                        a.need_capacity_kwh > 0 ? 'var(--tx-2)' : 'var(--ok)'],
                      ['이벤트당 순익', `+${won(a.event_net_won)}`, 'var(--ok)'],
                      [`연 수익 (${won(acmp.events_per_year)}일)`,
                        `+${won(a.year_net_won)}`, 'var(--ok)'],
                      [win ? '충전 할인 부담' : '배터리 열화 부담',
                        `−${won(win ? a.discount_cost_won : a.degradation_won)}`,
                        'var(--tx-3)'],
                    ] as [string, string, string][]).map(([k, v, c]) => (
                      <div className="jc-r" key={k}>
                        <span>{k}</span>
                        <b className="num" style={{ color: c }}>{v}</b>
                      </div>
                    ))}
                  </div>
                  <div className={`jc-over ${win ? 'good' : 'bad'}`}>
                    {a.payback_years === null ? '회수 불가'
                      : a.payback_years === 0 ? '첫 이벤트부터 흑자'
                      : `투자 회수 ${won(a.payback_years)}년`}
                  </div>
                </div>
              );
            })}
          </div>
          <p className="jeju-verdict">{acmp.verdict}</p>
          <p className="jo-note">{acmp.note}</p>
        </div>
      )}

      {/* ── 단지 현황 ── */}
      <div className="jo-sect">
        <div className="js-head">
          <b>단지별 여유</b>
          <span className="js-sub">
            기준선(계약전력·이번달 최대 중 높은 쪽)까지 남은 만큼만 충전할 수 있습니다
          </span>
        </div>
        <div className="jo-sites">
          {st.sites.map((s) => {
            const guard = Math.max(s.contract_kw, s.month_peak_kw);
            const loadPct = (s.base_load_kw / maxLoad) * 100;
            const headPct = (Math.max(0, guard - s.base_load_kw) / maxLoad) * 100;
            const usable = s.max_charge_kw > 0.5;
            return (
              <div className={`jo-site ${s.online ? '' : 'off'} ${s.live ? 'islive' : ''}`} key={s.id}>
                <div className="jo-sh">
                  <b>{s.name}</b>
                  {s.live
                    ? <span className="jo-live">LIVE</span>
                    : <span className="num">{s.id}</span>}
                </div>
                <div className="jo-bar-wrap" title={`부하 ${s.base_load_kw}kW / 기준 ${guard}kW`}>
                  <i className="lo" style={{ width: `${loadPct}%` }} />
                  <i className="hd" style={{ width: `${headPct}%` }} />
                </div>
                <div className="jo-sm">
                  <span>부하 <b className="num">{won(s.base_load_kw)}</b></span>
                  <span>기준 <b className="num">{won(guard)}</b></span>
                </div>
                <div className={`jo-cap ${usable ? 'ok' : 'no'}`}>
                  {s.online
                    ? usable ? `충전 가능 ${won(s.max_charge_kw)}kW` : '여유 없음'
                    : '통신 두절'}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── 급전 결과 ── */}
      {res && res.rows.length > 0 && (
        <div className="jo-sect">
          <div className="js-head">
            <b>급전 결과 — {res.mode === 'peak' ? '피크 여유 기반' : '균등 배분'}</b>
            <span className="js-sub">
              이행 {pct(res.delivery_rate)} · 커버리지 {pct(res.coverage)} ·
              순손익 ₩{won(res.net_won)}
            </span>
          </div>
          <table className="jeju-tb">
            <thead>
              <tr>
                <th>단지</th>
                <th className="r">지시</th>
                <th className="r">이행</th>
                <th className="r">충전 후 부하</th>
                <th className="r">기준선</th>
                <th className="r">초과</th>
                <th className="r">기본요금 영향</th>
              </tr>
            </thead>
            <tbody>
              {res.rows.map((r) => (
                <tr key={r.site}>
                  <td><b>{r.name}</b></td>
                  <td className="r num">{won(r.ordered_kw)}</td>
                  <td className="r num">{won(r.delivered_kw)}</td>
                  <td className="r num" style={{ color: r.peak_over_kw > 0 ? 'var(--crit)' : 'var(--tx-2)' }}>
                    {won(r.load_after_kw)}
                  </td>
                  <td className="r num">{won(r.guard_kw)}</td>
                  <td className="r num" style={{ color: r.peak_over_kw > 0 ? 'var(--crit)' : 'var(--tx-3)' }}>
                    {r.peak_over_kw > 0 ? `+${won(r.peak_over_kw)}` : '—'}
                  </td>
                  <td className="r num" style={{ color: r.peak_penalty_won > 0 ? 'var(--crit)' : 'var(--tx-3)' }}>
                    {r.peak_penalty_won > 0 ? `−${won(r.peak_penalty_won)}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="jeju-disc">
        <b>데이터 고지</b> — 이벤트 발생 시각·규모는 전력거래소 실측 분포(출력제어 335일,
        플러스DR 272건)에서 추출합니다. 정산 단가는 미공개이므로 가정값이며,
        위 입력창에서 바꿔가며 확인할 수 있습니다.
      </p>
    </div>
  );
}
