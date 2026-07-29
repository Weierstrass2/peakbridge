import { useCallback, useEffect, useState } from 'react';
import {
  consoleApi,
  type JejuLeaderboard,
  type JejuRow,
  type JejuSensitivity,
} from '../lib/api';

const won = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : Math.round(n).toLocaleString('ko-KR');

const signed = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : n > 0 ? `+${n}` : `${n}`;

const pos = (n: number | null | undefined) =>
  (n ?? 0) >= 0 ? 'var(--ok)' : 'var(--crit)';

/** 제주 실시간시장 데스크.
 *
 *  이 화면이 말하는 것은 하나다:
 *    육지 SMP 차익거래는 변동비를 넣으면 적자다.
 *    제주가 성립하는 이유는 전략이 똑똑해서가 아니라 '버려지는 전력'이 있어서다.
 *
 *  그래서 리더보드보다 민감도 표를 위에 둔다. 사업 성립 조건이 먼저다. */
export default function JejuPanel({
  onLog,
}: {
  onLog: (lv: 'info' | 'ok' | 'warn' | 'crit', msg: string) => void;
}) {
  const [lb, setLb] = useState<JejuLeaderboard | null>(null);
  const [sens, setSens] = useState<JejuSensitivity | null>(null);
  const [spread, setSpread] = useState(0.41);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (sc: number) => {
    setBusy(true);
    try {
      const [a, b] = await Promise.all([
        consoleApi.jejuLeaderboard(365, sc),
        consoleApi.jejuSensitivity(180),
      ]);
      setLb(a.data);
      setSens(b.data);
      const top = a.data.leaderboard?.[0];
      if (top) {
        onLog(
          'ok',
          `제주 RT 백테스트 — 1위 ${top.label} · 연 ₩${won(top.annual_won)} · ` +
            `마진 ${signed(top.margin_per_kwh)}/kWh · 공짜충전 ${Math.round(top.free_share * 100)}%`,
        );
      }
    } catch {
      onLog('warn', '제주 시장 백테스트 실패');
    } finally {
      setBusy(false);
    }
  }, [onLog]);

  useEffect(() => { load(spread); }, [load, spread]);

  const rows: JejuRow[] = lb?.leaderboard ?? [];
  const best = Math.max(1, ...rows.map((r) => Math.abs(r.annual_won)));
  const inland = sens?.inland_reference;

  return (
    <div className="jeju">
      {/* ── 왜 제주인가 — 변동비 대조 ── */}
      <div className="jeju-thesis">
        <div className="jt-col">
          <span className="jt-tag">육지 · 실측</span>
          <div className="jt-eq">
            <span>충전 {inland?.charge_unit_won ?? 42.5} ÷ 효율 0.9</span>
            <span>+ 열화 50</span>
            <b>= 변동비 {inland?.var_cost_won ?? 97.2}</b>
          </div>
          <div className="jt-out" style={{ color: 'var(--crit)' }}>
            최고가 {inland?.peak_won ?? 90.1} → 마진 {signed(inland?.margin_per_kwh ?? -7.1)}/kWh
          </div>
          <p className="jt-note">스프레드(47.6)가 열화비용(50)보다 작다. 팔수록 손해다.</p>
        </div>
        <div className="jt-arrow">→</div>
        <div className="jt-col">
          <span className="jt-tag on">제주 · 출력제어 흡수</span>
          <div className="jt-eq">
            <span>충전 0 ÷ 효율 0.9 (버려지는 전력)</span>
            <span>+ 열화 50</span>
            <b>= 변동비 50.0</b>
          </div>
          <div className="jt-out" style={{ color: 'var(--ok)' }}>
            같은 가격에 팔아도 마진 {signed(rows[0]?.margin_per_kwh ?? null)}/kWh
          </div>
          <p className="jt-note">
            발전사업자에겐 버릴 전력, 우리에겐 공짜 연료. 폐기물이 원료가 된다.
          </p>
        </div>
      </div>

      {/* ── 사업 성립 조건 (민감도) ── */}
      <div className="jeju-sect">
        <div className="js-head">
          <b>사업 성립 조건 — 출력제어 빈도 민감도</b>
          <span className="js-sub">수익은 알고리즘이 아니라 '버려지는 전력의 양'이 결정한다</span>
        </div>
        <table className="jeju-tb">
          <thead>
            <tr>
              <th>출력제어 시나리오</th>
              <th className="r">공짜 충전</th>
              <th className="r">실질 충전단가</th>
              <th className="r">마진/kWh</th>
              <th className="r">연간 손익</th>
            </tr>
          </thead>
          <tbody>
            {(sens?.rows ?? []).map((r) => (
              <tr key={r.scenario}>
                <td>{r.scenario}</td>
                <td className="r num">{Math.round(r.free_share * 100)}%</td>
                <td className="r num">₩{r.charge_unit_won}</td>
                <td className="r num" style={{ color: pos(r.margin_per_kwh) }}>
                  {signed(r.margin_per_kwh)}
                </td>
                <td className="r num" style={{ color: pos(r.annual_won) }}>
                  {won(r.annual_won)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {sens?.verdict && <p className="jeju-verdict">{sens.verdict}</p>}
      </div>

      {/* ── 전략 리더보드 ── */}
      <div className="jeju-sect">
        <div className="js-head">
          <b>제주 RT 전략 리더보드</b>
          <span className="js-sub">
            신호는 가격이 아니라 순부하 — 가격 예측보다 순부하 예측이 쉽다
          </span>
          <div className="js-ctl">
            <label className="label-cap">변동폭 가정</label>
            <input
              type="range" min={0.3} max={1.0} step={0.01} value={spread}
              onChange={(e) => setSpread(Number(e.target.value))}
              disabled={busy}
            />
            <span className="num">×{spread.toFixed(2)}</span>
            <span className="js-hint">
              {spread <= 0.45 ? '육지 실측 수준 (보수적)' : spread >= 0.8 ? '고변동 가정' : '중간'}
            </span>
          </div>
        </div>
        <table className="jeju-tb">
          <thead>
            <tr>
              <th>전략</th>
              <th className="r">연간 손익</th>
              <th className="r">마진/kWh</th>
              <th className="r">공짜충전</th>
              <th className="r">승률</th>
              <th className="r">Sharpe</th>
              <th className="r">MDD</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.strategy} className={i === 0 ? 'top' : ''}>
                <td>
                  <b>{r.label}</b>
                  <div className="jeju-bar">
                    <i
                      style={{
                        width: `${(Math.abs(r.annual_won) / best) * 100}%`,
                        background: pos(r.annual_won),
                      }}
                    />
                  </div>
                </td>
                <td className="r num" style={{ color: pos(r.annual_won) }}>{won(r.annual_won)}</td>
                <td className="r num" style={{ color: pos(r.margin_per_kwh) }}>
                  {signed(r.margin_per_kwh)}
                </td>
                <td className="r num">{Math.round(r.free_share * 100)}%</td>
                <td className="r num">{Math.round(r.hit_rate * 100)}%</td>
                <td className="r num">{r.sharpe ?? '—'}</td>
                <td className="r num">{won(r.max_drawdown_won)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── 손익 분해 (1위 전략) ── */}
      {rows[0] && (
        <div className="jeju-sect">
          <div className="js-head">
            <b>손익 분해 — {rows[0].label}</b>
            <span className="js-sub">충전비용을 뺀 실질 손익. 이전 백테스트엔 이 항이 없었다</span>
          </div>
          <div className="jeju-attr">
            {([
              ['방전 매출', rows[0].revenue_won, 'var(--ok)'],
              ['충전 비용', -rows[0].charge_cost_won, 'var(--warn)'],
              ['배터리 열화', -rows[0].degradation_won, 'var(--crit)'],
              ['순손익', rows[0].annual_won, 'var(--acc)'],
            ] as [string, number, string][]).map(([k, v, c]) => (
              <div className="ja-item" key={k}>
                <span className="k">{k}</span>
                <b style={{ color: c }}>{won(v)}</b>
              </div>
            ))}
          </div>
          <div className="jeju-flow">
            방전 {won(rows[0].discharge_kwh)}kWh · 충전 {won(rows[0].charge_kwh)}kWh
            (그중 출력제어 흡수 <b style={{ color: 'var(--ok)' }}>{won(rows[0].free_kwh)}kWh</b>)
            · 일평균 출력제어 {rows[0].avg_curtail_slots}/96슬롯
          </div>
        </div>
      )}

      {lb?.disclaimer && (
        <p className="jeju-disc">
          <b>데이터 고지</b> — {lb.disclaimer}
        </p>
      )}
    </div>
  );
}
