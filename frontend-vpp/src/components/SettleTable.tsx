import { useEffect, useState } from 'react';
import { consoleApi, type LedgerEntry, type LedgerSummary } from '../lib/api';

type Contracts = Awaited<ReturnType<typeof consoleApi.vppContracts>>['data'];

const fmtW = (n: number) => Math.round(n).toLocaleString('ko-KR');

export default function SettleTable() {
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [summary, setSummary] = useState<LedgerSummary | null>(null);
  const [con, setCon] = useState<Contracts | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const { data } = await consoleApi.ledgerFull(50);
        if (alive) { setEntries(data.entries); setSummary(data.summary); }
      } catch { /* noop */ }
      try {
        const { data } = await consoleApi.vppContracts();
        setCon(data);
      } catch { /* noop */ }
    };
    load();
    const t = setInterval(load, 10_000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  return (
    <div className="settle">
      <div className="settle-sum">
        <span>금일 거래 <b>{summary?.today_trades ?? 0}건</b></span>
        <span>금일 물량 <b>{summary?.today_kwh ?? 0} kWh</b></span>
        <span>금일 수익 <b style={{ color: 'var(--ok)' }}>₩{summary ? fmtW(summary.today_revenue) : 0}</b></span>
        <span>누적 수익 <b style={{ color: 'var(--ok)' }}>₩{summary ? fmtW(summary.total_revenue) : 0}</b></span>
        {summary?.by_type && Object.entries(summary.by_type).map(([k, v]) => (
          <span key={k} style={{ color: 'var(--tx-3)' }}>
            {k} <b style={{ color: v >= 0 ? 'var(--tx-2)' : 'var(--crit)' }}>₩{fmtW(v)}</b>
          </span>
        ))}
      </div>
      {con && (
        <div className="contract-strip">
          <div className="con-split">
            <span>총 정산 <b>₩{fmtW(con.settlement_split.total_revenue)}</b></span>
            <span>단지 배분 <b style={{ color: 'var(--acc)' }}>₩{fmtW(con.settlement_split.site_payout)}</b></span>
            <span>플랫폼 매출 <b style={{ color: 'var(--ok)' }}>₩{fmtW(con.settlement_split.platform_revenue)}</b> <i>(평균 {Math.round(con.settlement_split.avg_platform_share * 100)}%)</i></span>
          </div>
          <div className="con-cards">
            {con.contracts.map((c) => (
              <div key={c.building_id} className="con-card">
                <div className="con-top">
                  <b>{c.name}</b>
                  <span className="mode">{c.status}</span>
                </div>
                <div className="con-body">
                  {c.type} · 단지 {Math.round(c.site_share * 100)} / 플랫폼 {Math.round(c.platform_share * 100)}
                </div>
                <div className="con-meta">{c.term} · {c.resources}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="settle-scroll">
        <table className="dg">
          <thead>
            <tr>
              <th>TIME</th><th>TYPE</th><th>DETAIL</th>
              <th className="num">kWh</th><th className="num">REVENUE</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr><td colSpan={5} style={{ color: 'var(--tx-3)' }}>정산 기록 없음 — DR 발령 시 자동 기록</td></tr>
            )}
            {entries.map((e) => (
              <tr key={e.id}>
                <td className="num" style={{ textAlign: 'left', color: 'var(--tx-3)' }}>{e.ts.slice(5, 19).replace('T', ' ')}</td>
                <td>
                  <span className="mode" style={{ color: e.type === 'DR정산' ? 'var(--warn)' : 'var(--acc)', borderColor: 'currentcolor' }}>
                    {e.type}
                  </span>
                </td>
                <td style={{ color: 'var(--tx-2)', maxWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.detail}</td>
                <td className="num">{e.kwh}</td>
                <td className="num" style={{ color: e.revenue >= 0 ? 'var(--ok)' : 'var(--tx-3)' }}>
                  {e.revenue >= 0 ? '+' : '−'}₩{fmtW(Math.abs(e.revenue))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
