import { useEffect, useState } from 'react';
import {
  consoleApi,
  type DrEventResult,
  type LedgerEntry,
  type LedgerSummary,
} from '../lib/api';

const LEVELS = [
  { v: 0, label: 'LV0', desc: '해제', crit: false },
  { v: 1, label: 'LV1', desc: '30%', crit: false },
  { v: 2, label: 'LV2', desc: '70%', crit: false },
  { v: 3, label: 'LV3', desc: '100%', crit: true },
];

const fmtW = (n: number) => `${Math.round(n).toLocaleString('ko-KR')}`;

export default function DrPanel({
  onLog,
}: {
  onLog: (lv: 'info' | 'ok' | 'warn' | 'crit', msg: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<DrEventResult | null>(null);
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [summary, setSummary] = useState<LedgerSummary | null>(null);

  const refresh = async () => {
    try {
      const { data } = await consoleApi.drStatus();
      setActive(data.active_event);
    } catch { /* noop */ }
    try {
      const { data } = await consoleApi.ledgerFull(6);
      setEntries(data.entries);
      setSummary(data.summary);
    } catch { /* noop */ }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10_000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const issue = async (type: string, value: number, desc: string) => {
    setBusy(true);
    try {
      const ev = await consoleApi.issueDr(type, value);
      onLog(value >= 2 && type === 'SIMPLE' ? 'crit' : 'ok', `발령 ${desc} — ${ev.label} [${ev.event_id}]`);
      await refresh();
    } catch {
      onLog('warn', `발령 실패 — ${desc} (백엔드 미응답)`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="drops">
      <div className="dr-cap">신호 발령 — OpenADR SIMPLE</div>
      <div className="dr-btns">
        {LEVELS.map((l) => (
          <button
            key={l.v}
            className={`cbtn ${l.crit ? 'crit' : ''}`}
            disabled={busy}
            onClick={() => issue('SIMPLE', l.v, `SIMPLE ${l.v}`)}
          >
            <b>{l.label}</b>
            <span>{l.desc}</span>
          </button>
        ))}
      </div>

      <div className="dr-cap" style={{ marginTop: 10 }}>가격 신호 — PRICE</div>
      <div className="dr-btns two">
        <button className="cbtn" disabled={busy} onClick={() => issue('PRICE', 210, 'PRICE 210')}>
          <b>210₩</b><span>방전</span>
        </button>
        <button className="cbtn" disabled={busy} onClick={() => issue('PRICE', 50, 'PRICE 50')}>
          <b>50₩</b><span>충전</span>
        </button>
      </div>

      <div className={`dr-active ${active ? 'on' : ''}`}>
        {active
          ? `활성 — ${active.label} [${active.event_id}]`
          : '활성 이벤트 없음'}
      </div>

      <div className="dr-cap ledger-cap">
        정산 원장
        <span>
          금일 {summary?.today_trades ?? 0}건&ensp;
          <b style={{ color: 'var(--ok)' }}>₩{summary ? fmtW(summary.today_revenue) : '0'}</b>
        </span>
      </div>
      <div className="ledger">
        {entries.length === 0 && <div className="ledger-empty">정산 기록 없음</div>}
        {entries.map((e) => (
          <div key={e.id} className="ledger-row">
            <span className="ts">{e.ts.slice(11, 19)}</span>
            <span className={`ty ${e.type === 'DR정산' ? 'dr' : 'arb'}`}>{e.type}</span>
            <span className="kwh">{e.kwh}kWh</span>
            <span className={`rev ${e.revenue >= 0 ? 'pos' : 'neg'}`}>
              {e.revenue >= 0 ? '+' : '−'}₩{fmtW(Math.abs(e.revenue))}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
