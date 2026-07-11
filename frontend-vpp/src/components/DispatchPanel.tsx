import { useEffect, useState } from 'react';
import { consoleApi, type DispatchStatus } from '../lib/api';

const fmtW = (n: number) => Math.round(n).toLocaleString('ko-KR');

export default function DispatchPanel({
  onLog,
}: {
  onLog: (lv: 'info' | 'ok' | 'warn' | 'crit', msg: string) => void;
}) {
  const [st, setSt] = useState<DispatchStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await consoleApi.dispatchStatus();
      setSt(data);
    } catch { /* noop */ }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);   // RTU 주기 동기
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activate = async () => {
    setBusy(true);
    try {
      const r = await consoleApi.dispatchActivate();
      if ('error' in r && r.error) onLog('warn', r.error);
      else onLog('crit', '급전 스케줄 활성화 — 가속 이행 시작 (60×)');
      await load();
    } catch {
      onLog('warn', '급전 활성화 실패');
    } finally {
      setBusy(false);
    }
  };

  const a = st?.active ?? null;
  const awarded = a?.hours.filter((h) => h.awarded) ?? [];

  return (
    <div className="dispatch">
      <div className="dp-head">
        <div className="dp-meta">
          {st?.market_types.map((m) => (
            <span key={m.id} className={`mkt-state ${m.state === '운영' ? 'on' : ''}`}>
              {m.id} <i>{m.state}</i>
            </span>
          ))}
        </div>
        <div className="dp-rtu">
          RTU HB <b>#{st?.rtu.seq ?? 0}</b> · {st?.rtu.interval_s ?? 4}s
          <span className="dot live" style={{ marginLeft: 6 }} />
        </div>
      </div>

      {!a ? (
        <div className="dp-empty">
          <p>활성 급전 스케줄 없음</p>
          <button className="cbtn wide" disabled={busy} onClick={activate}>
            <b>낙찰 스케줄 활성화</b><span>가속 60×</span>
          </button>
          <p className="dp-hint">입찰 데스크에서 개찰 완료 후 활성화</p>
        </div>
      ) : (
        <>
          <div className="dp-summary">
            <span>시장시각 <b className="simclock">{a.sim_clock}</b> <i>({a.time_scale}× 가속)</i></span>
            <span>정산 <b>{a.settled_hours}/{a.awarded_hours}</b></span>
            <span>급전수익 <b style={{ color: 'var(--ok)' }}>₩{fmtW(a.energy_revenue)}</b></span>
            <span>CP <b style={{ color: 'var(--acc)' }}>₩{fmtW(a.cp_revenue)}</b></span>
            <span>위약 <b style={{ color: 'var(--crit)' }}>−₩{fmtW(a.penalties)}</b></span>
            <span>순수익 <b style={{ color: a.net >= 0 ? 'var(--ok)' : 'var(--crit)' }}>₩{fmtW(a.net)}</b></span>
          </div>
          <div className="dp-scroll">
            <table className="dg">
              <thead>
                <tr>
                  <th>구간</th><th className="num">낙찰 kW</th><th className="num">MCP</th>
                  <th className="num">이행 kWh</th><th className="num">이행률</th><th>상태</th>
                </tr>
              </thead>
              <tbody>
                {awarded.map((h) => (
                  <tr key={h.hour} className={h.status === '이행중' ? 'row-firing' : ''}>
                    <td className="num" style={{ textAlign: 'left', color: 'var(--tx-3)' }}>
                      {String(h.hour).padStart(2, '0')}:00
                    </td>
                    <td className="num">{h.qty_kw}</td>
                    <td className="num" style={{ color: 'var(--warn)' }}>{h.mcp.toFixed(1)}</td>
                    <td className="num">{h.delivered_kwh.toFixed(1)}</td>
                    <td className="num">
                      {h.compliance !== undefined ? `${h.compliance}%`
                        : h.status === '이행중' ? `${h.progress ?? 0}%` : '—'}
                    </td>
                    <td>
                      <span className={`dstat ${
                        h.status === '완료' ? 'ok' : h.status === '이행중' ? 'firing' : h.status === '부족' ? 'bad' : ''
                      }`}>{h.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="dp-soc">
            {Object.entries(st?.soc ?? {}).map(([k, v]) => (
              <span key={k}>
                {k.replace('building-', '단지 ')} SOC
                <b style={{ color: v < 25 ? 'var(--crit)' : 'var(--tx-1)' }}> {v}%</b>
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
