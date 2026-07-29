import { useCallback, useEffect, useState } from 'react';
import { consoleApi, type PeakReservation } from '../lib/api';

const won = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : Math.round(n).toLocaleString('ko-KR');

/** 피크 예약 — 입찰 전에 본업(기본요금 방어)부터 확보한다.
 *
 *  이 패널이 답하는 질문은 하나다:
 *      "관리비 아끼는 게 본업이라면서, 왜 배터리를 시장에 다 팔지?"
 *
 *  배터리 1kWh를 시장에 팔면 시장가를 벌지만, 같은 1kWh로 피크를 깎으면
 *  기본요금이 한 달 내내 줄어든다. 단위가 다르기 때문에 가치가 10배 넘게 벌어진다.
 *  그래서 피크 위험일에는 **팔지 않는 것이 최적**이다. */
export default function PeakReserve({
  onLog,
}: {
  onLog?: (lv: 'info' | 'ok' | 'warn' | 'crit', msg: string) => void;
}) {
  const [d, setD] = useState<PeakReservation | null>(null);
  const [contract, setContract] = useState(200);
  const [monthPeak, setMonthPeak] = useState(0);
  const [lookback, setLookback] = useState(1);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const { data } = await consoleApi.peakReservation(contract, monthPeak, lookback);
      setD(data);
      onLog?.(
        data.reserved_kwh > 0 ? 'warn' : 'ok',
        data.reserved_kwh > 0
          ? `피크 예약 — ${won(data.reserved_kwh)}kWh 잠금 · 판매가능 ${won(data.sellable_kwh)}kWh · ${data.comparison.verdict}`
          : `피크 예약 없음 — 전량 ${won(data.sellable_kwh)}kWh 판매 가능`,
      );
    } catch { onLog?.('warn', '피크 예약 계산 실패'); }
    finally { setBusy(false); }
  }, [contract, monthPeak, lookback, onLog]);

  useEffect(() => { load(); }, [load]);

  if (!d) return <div className="pkr"><p className="prof-load">피크 예약 계산 중…</p></div>;

  const locked = d.reserved_kwh > 0;
  const maxD = Math.max(d.contract_kw, ...d.demand_kw, 1);

  return (
    <div className="pkr">
      {/* 판정 배너 */}
      <div className={`pkr-banner ${locked ? 'lock' : 'free'}`}>
        <b>{locked ? '배터리 예약 — 시장 판매 제한' : '예약 없음 — 전량 판매 가능'}</b>
        <span>{d.comparison.verdict}</span>
      </div>

      {/* 핵심 수치 */}
      <div className="pkr-kpis">
        {([
          ['예상 최대수요', `${won(d.expected_peak_kw)} kW`, d.renews_month_peak ? 'var(--crit)' : 'var(--tx-1)'],
          ['계약전력', `${won(d.contract_kw)} kW`, 'var(--tx-2)'],
          ['깎을 양', `${won(d.shave_kw)} kW`, 'var(--warn)'],
          ['예약 에너지', `${won(d.reserved_kwh)} kWh`, locked ? 'var(--warn)' : 'var(--tx-3)'],
          ['판매 가능', `${won(d.sellable_kwh)} kWh`, 'var(--ok)'],
        ] as [string, string, string][]).map(([k, v, c]) => (
          <div className="desk-kpi" key={k}>
            <span className="k">{k}</span>
            <b style={{ color: c }}>{v}</b>
          </div>
        ))}
      </div>

      {/* 기회비용 대조 — 이 패널의 핵심 */}
      <div className="pkr-vs">
        <div className="pv-side">
          <span className="label-cap">시장에 팔면</span>
          <b className="num">₩{won(d.comparison.market_won_per_kwh)}</b>
          <span className="pv-u">/kWh · 1회성</span>
        </div>
        <div className="pv-mid">vs</div>
        <div className="pv-side win">
          <span className="label-cap">피크에 쓰면</span>
          <b className="num">₩{won(d.comparison.peak_won_per_kwh)}</b>
          <span className="pv-u">
            /kWh · 기본요금 {lookback > 1 ? `${lookback}개월` : '한 달'} 지속
          </span>
        </div>
        {d.comparison.ratio && (
          <div className="pv-ratio">
            <b>{d.comparison.ratio}배</b>
            <span>피크쉐이빙 우위</span>
          </div>
        )}
      </div>

      {/* 시간대별 부하 + 예약 구간 */}
      <div className="pkr-chart">
        {d.demand_kw.map((v, h) => {
          const over = v > d.contract_kw;
          const black = d.blackout_hours.includes(h);
          return (
            <div className="pk-col" key={h} title={`${h}시 · ${won(v)}kW${black ? ' · 판매 금지' : ''}`}>
              <div className="pk-bar" style={{ height: `${(v / maxD) * 100}%` }}>
                <i style={{ background: black ? 'var(--crit)' : over ? 'var(--warn)' : 'var(--acc)' }} />
              </div>
              {h % 3 === 0 && <span className="pk-x">{h}</span>}
            </div>
          );
        })}
        <div className="pk-line" style={{ bottom: `${(d.contract_kw / maxD) * 100}%` }}>
          <span>계약전력 {won(d.contract_kw)}kW</span>
        </div>
      </div>

      {/* 조건 조정 */}
      <div className="pkr-ctl">
        <label>
          계약전력
          <input type="number" value={contract} min={50} step={10} disabled={busy}
                 onChange={(e) => setContract(Number(e.target.value))} />
          kW
        </label>
        <label>
          이번 달 최대수요
          <input type="number" value={monthPeak} min={0} step={10} disabled={busy}
                 onChange={(e) => setMonthPeak(Number(e.target.value))} />
          kW
        </label>
        <label>
          기본요금 산정
          <select value={lookback} disabled={busy}
                  onChange={(e) => setLookback(Number(e.target.value))}>
            <option value={1}>당월 최대</option>
            <option value={12}>직전 12개월 최대</option>
          </select>
        </label>
        <span className="pkr-hint">
          요금제에 따라 다름 — 12개월 방식이면 한 번 놓친 피크가 1년을 따라간다
        </span>
      </div>
    </div>
  );
}
