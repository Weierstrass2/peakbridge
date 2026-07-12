import { useEffect, useState } from 'react';
import { consoleApi } from '../lib/api';

interface Alarm { id: string; ts: string; severity: string; source: string; msg: string; ack: boolean; }
interface AuditEntry { ts: string; actor: string; action: string; detail: string; }
interface Risk { status: string; usable_kwh: number; obligation_kwh: number; coverage: number; }

const SEV_COLOR: Record<string, string> = { CRIT: 'var(--crit)', WARN: 'var(--warn)', INFO: 'var(--acc)' };
const RISK_COLOR: Record<string, string> = { '안전': 'var(--ok)', '주의': 'var(--warn)', '위험': 'var(--crit)' };

export default function OpsPanel() {
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [unack, setUnack] = useState(0);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [risk, setRisk] = useState<Risk | null>(null);

  const load = async () => {
    try {
      const { data } = await consoleApi.opsAlarms();
      setAlarms(data.items); setUnack(data.unack);
    } catch { /* noop */ }
    try {
      const { data } = await consoleApi.opsAudit();
      setAudit(data.entries);
    } catch { /* noop */ }
    try {
      const { data } = await consoleApi.opsRisk();
      setRisk(data);
    } catch { /* noop */ }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ack = async (id: string) => {
    try { await consoleApi.opsAck(id, localStorage.getItem('op_name') ?? 'operator'); await load(); } catch { /* noop */ }
  };

  return (
    <div className="ops">
      <div className="ops-col">
        <div className="dr-cap">
          알람 큐 <span style={{ color: unack > 0 ? 'var(--crit)' : 'var(--tx-3)' }}>미확인 {unack}</span>
        </div>
        <div className="ops-scroll">
          {alarms.length === 0 && <div className="ledger-empty">알람 없음</div>}
          {alarms.map((a) => (
            <div key={a.id} className={`alarm-row ${a.ack ? 'acked' : ''}`}>
              <span className="al-sev" style={{ color: SEV_COLOR[a.severity] ?? 'var(--tx-2)' }}>
                {a.severity}
              </span>
              <div className="al-body">
                <div className="al-msg">{a.msg}</div>
                <div className="al-meta">{a.ts.slice(11, 19)} · {a.source}</div>
              </div>
              {!a.ack && (
                <button className="al-ack" onClick={() => ack(a.id)}>ACK</button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="ops-col">
        <div className="dr-cap">이행 리스크 (B2)</div>
        {risk && (
          <div className="risk-card">
            <div className="risk-status" style={{ color: RISK_COLOR[risk.status] }}>
              {risk.status}
            </div>
            <div className="risk-bar">
              <i style={{
                width: `${Math.min(100, risk.coverage * 50)}%`,
                background: RISK_COLOR[risk.status],
              }} />
            </div>
            <div className="risk-rows">
              <span>가용 에너지 <b>{risk.usable_kwh} kWh</b></span>
              <span>낙찰 의무 잔량 <b>{risk.obligation_kwh} kWh</b></span>
              <span>커버리지 <b style={{ color: RISK_COLOR[risk.status] }}>{(risk.coverage * 100).toFixed(0)}%</b></span>
            </div>
            <p className="risk-note">
              커버리지 105% 미만 시 주의, 70% 미만 시 위험 알람 자동 발보
            </p>
          </div>
        )}
      </div>

      <div className="ops-col">
        <div className="dr-cap">감사 로그 (B4)</div>
        <div className="ops-scroll">
          {audit.length === 0 && <div className="ledger-empty">기록 없음</div>}
          {audit.map((e, i) => (
            <div key={i} className="audit-row">
              <span className="au-ts">{e.ts.slice(5, 19).replace('T', ' ')}</span>
              <span className="au-act">{e.action}</span>
              <span className="au-det">{e.detail}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
