import { useEffect, useState } from 'react';
import { consoleApi, type Bid, type StrategyInfo } from '../lib/api';

const fmtW = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : Math.round(n).toLocaleString('ko-KR');

const FAMILY_LABEL: Record<string, { t: string; c: string }> = {
  rule: { t: '규칙', c: 'var(--tx-2)' },
  optimize: { t: '최적화', c: 'var(--acc)' },
  statistical: { t: '통계', c: 'var(--ok)' },
  learned: { t: '학습', c: 'var(--vio)' },
  meta: { t: '메타', c: 'var(--warn)' },
};

/** 전략 선택기 — 백테스트 리더보드에서 고른 알고리즘으로 입찰서를 채운다.
 *
 *  퀀트의 전략 배포 화면과 같은 역할이다: 성과지표를 보고 고르면
 *  해당 전략이 24구간 입찰을 만들어 데스크에 적용된다. */
export default function StrategyPicker({
  onApply,
  onLog,
}: {
  onApply: (bids: Bid[]) => void;
  onLog: (lv: 'info' | 'ok' | 'warn' | 'crit', msg: string) => void;
}) {
  const [items, setItems] = useState<StrategyInfo[]>([]);
  const [active, setActive] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const load = async () => {
    try {
      const { data } = await consoleApi.strategies();
      setItems(data.strategies);
      setActive(data.active);
    } catch {
      /* 백엔드 미배포 시 조용히 숨긴다 */
    }
  };

  useEffect(() => { load(); }, []);

  const apply = async (name: string) => {
    setBusy(true);
    try {
      const { data } = await consoleApi.strategyBids(name);
      onApply(data.bids);
      await consoleApi.strategyActivate(name).catch(() => undefined);
      setActive(name);
      const bt = data.backtest;
      onLog(
        'ok',
        `전략 적용: ${name} — ${data.description} · 백테스트 일평균 ₩${fmtW(bt.daily_mean_won)}` +
          (bt.sharpe ? ` · Sharpe ${bt.sharpe}` : '') +
          ` · 가용 ${data.usable_kwh}kWh 제약 반영`,
      );
      setOpen(false);
    } catch {
      onLog('warn', `전략 적용 실패: ${name}`);
    } finally {
      setBusy(false);
    }
  };

  if (items.length === 0) return null;

  const cur = items.find((s) => s.name === active);
  const best = items[0];

  return (
    <div className="stratbar">
      <button className="strat-toggle" onClick={() => setOpen((v) => !v)} type="button">
        <span className="k">전략</span>
        <b>{active || '—'}</b>
        <span className="mini">
          일평균 ₩{fmtW(cur?.daily_mean_won)}
          {cur?.sharpe ? ` · SR ${cur.sharpe}` : ''}
        </span>
        <span className="caret">{open ? '▴' : '▾'}</span>
      </button>

      {!open && best && best.name !== active && (
        <span className="strat-hint">
          리더보드 1위 <b>{best.name}</b> ₩{fmtW(best.daily_mean_won)}
        </span>
      )}

      {open && (
        <div className="strat-table">
          <table className="dg">
            <thead>
              <tr>
                <th>전략</th>
                <th>계열</th>
                <th className="num">일평균 ₩</th>
                <th className="num">Sharpe</th>
                <th className="num">MDD ₩</th>
                <th className="num">이행률</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((s) => {
                const fam = FAMILY_LABEL[s.family] ?? { t: s.family, c: 'var(--tx-3)' };
                const neg = (s.daily_mean_won ?? 0) < 0;
                return (
                  <tr key={s.name} className={s.name === active ? 'on' : ''}>
                    <td>
                      <b>{s.name}</b>
                      <div className="desc">{s.description}</div>
                    </td>
                    <td style={{ color: fam.c }}>{fam.t}</td>
                    <td className="num" style={{ color: neg ? 'var(--crit)' : 'var(--ok)' }}>
                      {fmtW(s.daily_mean_won)}
                    </td>
                    <td className="num">{s.sharpe ?? '—'}</td>
                    <td className="num" style={{ color: 'var(--tx-2)' }}>{fmtW(s.max_drawdown_won)}</td>
                    <td className="num" style={{ color: (s.fill_rate ?? 1) < 0.9 ? 'var(--warn)' : 'var(--tx-2)' }}>
                      {s.fill_rate === null ? '—' : `${Math.round(s.fill_rate * 100)}%`}
                    </td>
                    <td>
                      <button
                        className="cbtn tiny"
                        disabled={busy}
                        onClick={() => apply(s.name)}
                        type="button"
                      >
                        적용
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="strat-note">
            150일 홀드아웃 백테스트 · 예측오차 σ=10% · 가용에너지 불확실성 σ=25% 반영.
            상위 3개 전략은 신뢰구간이 겹쳐 통계적으로 구분되지 않습니다.
          </div>
        </div>
      )}
    </div>
  );
}
