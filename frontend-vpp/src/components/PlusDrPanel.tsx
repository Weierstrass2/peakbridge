import { useCallback, useEffect, useState } from 'react';
import { consoleApi, type PlusDrReport } from '../lib/api';

const won = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : Math.round(n).toLocaleString('ko-KR');
const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
const pos = (n: number) => (n >= 0 ? 'var(--ok)' : 'var(--crit)');

/** 제주 플러스 DR — 전력거래소 실측 기반.
 *
 *  이 화면은 우리가 틀렸던 것을 바로잡은 결과다.
 *  처음엔 "출력제어 = 남는 전기 = 공짜 연료"라고 봤는데,
 *  실측에서 출력제어 시각 SMP가 평균 173원이었다. 공짜 전기는 없었다.
 *
 *  대신 진짜 시장을 찾았다 — 플러스 DR. 그리고 그 시장은 비어 있다. */
export default function PlusDrPanel({
  onLog,
}: {
  onLog: (lv: 'info' | 'ok' | 'warn' | 'crit', msg: string) => void;
}) {
  const [d, setD] = useState<PlusDrReport | null>(null);
  const [incentive, setIncentive] = useState(120);
  const [sites, setSites] = useState(100);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const { data } = await consoleApi.jejuPlusDr(incentive, sites);
      setD(data);
      const best = data.leaderboard[0];
      onLog(
        best && best.net_won > 0 ? 'ok' : 'warn',
        `플러스 DR — 1위 ${best?.label} · 이행률 ${pct(best?.delivery_rate ?? 0)} · ` +
          `연 ₩${won(best?.net_won)} (손익분기 ₩${data.assumption.breakeven_managed}/kWh)`,
      );
    } catch { onLog('warn', '플러스 DR 분석 실패'); }
    finally { setBusy(false); }
  }, [incentive, sites, onLog]);

  useEffect(() => { load(); }, [load]);

  if (!d) return <div className="pdr"><p className="prof-load">플러스 DR 분석 중…</p></div>;

  const f = d.facts;
  const a = d.assumption;
  const maxAbs = Math.max(1, ...d.leaderboard.map((r) => Math.abs(r.net_won)));

  return (
    <div className="pdr">
      {/* ── 전제 뒤집기 ── */}
      <div className="pdr-flip">
        <div className="pf-col wrong">
          <span className="pf-tag">우리가 처음 가정한 것</span>
          <b>출력제어 = 남는 전기 = 가격 0원</b>
          <span className="pf-d">버려지는 전력을 공짜로 받아 저장한다</span>
        </div>
        <div className="pf-x">✕</div>
        <div className="pf-col right">
          <span className="pf-tag on">전력거래소 실측</span>
          <b>출력제어 시각 SMP 평균 ₩{f.smp_mean} (최저 ₩{f.smp_min})</b>
          <span className="pf-d">
            SMP는 한계 발전기(LNG·중유) 변동비로 정해진다.
            재생에너지가 잘려나가도 가격은 그대로다. <b>공짜 전기는 없다.</b>
          </span>
        </div>
      </div>

      {/* ── 그래서 진짜 시장 ── */}
      <div className="pdr-sect">
        <div className="js-head">
          <b>그래서 정부는 가격 대신 인센티브를 쓴다 — 플러스 DR</b>
          <span className="js-sub">
            실측 {f._records}건 · {f._years?.join('~')} · 전력거래소
          </span>
        </div>
        <div className="pdr-gap">
          <div className="pg-item">
            <span className="k">낙찰률</span>
            <b style={{ color: 'var(--ok)' }}>{pct(f.clearing_rate)}</b>
            <span className="pg-d">입찰하면 전부 낙찰 — <b>경쟁이 없다</b></span>
          </div>
          <div className="pg-arrow">→</div>
          <div className="pg-item">
            <span className="k">이행률</span>
            <b style={{ color: 'var(--crit)' }}>{pct(f.delivery_rate)}</b>
            <span className="pg-d">
              중앙값 {f.delivery_pct_median}% · 100% 달성 {pct(f.full_delivery_share)}
              <br />낙찰자도 <b>지키지 못한다</b>
            </span>
          </div>
        </div>
      </div>

      {/* ── 왜 못 지키나 — 이 화면의 핵심 ── */}
      <div className="pdr-sect">
        <div className="js-head">
          <b>왜 못 지키나 — 이행하면 손해이기 때문이다</b>
          <span className="js-sub">이벤트 시간대 {f.event_hours.join('·')}시 = 최대부하 시간대</span>
        </div>
        <p className="pdr-why">
          플러스 DR은 <b>11~16시에 전기를 더 쓰라</b>고 요구한다. 그런데 그 시간은
          <b> 최대부하 시간대</b>다. 충전하면 계량기 피크가 올라가고,
          기본요금은 <b>그달 최고 순간 하나</b>로 정해진다.
          한 번 참여했다가 <b>그달 내내 더 낸다.</b>
        </p>
        <div className="pdr-be">
          <div className="pb-item bad">
            <span className="k">피크 관리 없이</span>
            <b>₩{won(a.breakeven_unmanaged)}</b>
            <span className="pb-d">/kWh 이상 받아야 본전 — 불가능</span>
          </div>
          <div className="pb-item good">
            <span className="k">피크 예약 적용</span>
            <b>₩{a.breakeven_managed}</b>
            <span className="pb-d">/kWh — 현실적인 수준</span>
          </div>
        </div>
        <p className="jeju-verdict">
          이 시장의 진짜 문제는 <b>“더 쓸 수 있느냐”</b>가 아니라
          <b> “피크를 올리지 않고 더 쓸 수 있느냐”</b>다. 우리는 그걸 계산할 수 있다.
        </p>
      </div>

      {/* ── 전략 비교 ── */}
      <div className="pdr-sect">
        <div className="js-head">
          <b>연간 손익 — {d.fleet.sites}단지 / {d.fleet.power_mw}MW</b>
          <span className="js-sub">
            이벤트 연 {f.event_days_per_year}회 · 건당 {f.avg_cleared_per_event_mwh}MWh
          </span>
        </div>
        <table className="jeju-tb">
          <thead>
            <tr>
              <th>참여 주체</th>
              <th className="r">이행률</th>
              <th className="r">증대량</th>
              <th className="r">연간 손익</th>
            </tr>
          </thead>
          <tbody>
            {d.leaderboard.map((r, i) => (
              <tr key={r.strategy} className={i === 0 ? 'top' : ''}>
                <td>
                  <b>{r.label}</b>
                  <div className="pc-note">{r.description}</div>
                  <div className="jeju-bar">
                    <i style={{
                      width: `${(Math.abs(r.net_won) / maxAbs) * 100}%`,
                      background: pos(r.net_won),
                    }} />
                  </div>
                </td>
                <td className="r num">{pct(r.delivery_rate)}</td>
                <td className="r num">{r.delivered_mwh} MWh</td>
                <td className="r num" style={{ color: pos(r.net_won) }}>{won(r.net_won)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── 조건 조정 ── */}
      <div className="pkr-ctl">
        <label>
          인센티브 가정
          <input type="number" value={incentive} min={0} step={10} disabled={busy}
                 onChange={(e) => setIncentive(Number(e.target.value))} />
          ₩/kWh
        </label>
        <label>
          참여 단지
          <input type="number" value={sites} min={10} step={10} disabled={busy}
                 onChange={(e) => setSites(Number(e.target.value))} />
          곳
        </label>
        <span className="pkr-hint">
          정산 단가는 미공개 — 가정값이며 손익분기와 함께 표시한다
        </span>
      </div>

      <p className="jeju-disc"><b>데이터 고지</b> — {d.disclaimer}</p>
    </div>
  );
}
