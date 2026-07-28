import type { Telemetry } from '../lib/api';

// v2 필드 (INA226 확장 자리) — 미장착 시 null로 오며 "—"로 표시한다.
export function EssPanel({ latest }: { latest: Telemetry | null }) {
  const rows: [string, number | null | undefined, string][] = [
    ['배터리 전압', latest?.battery_voltage_v, 'V'],
    ['ESS 전류', latest?.ess_current_a, 'A'],
    ['ESS 출력', latest?.ess_power_w, 'W'],
    // INA226 = 실기 펌웨어의 복귀 판단 센서. 대기 ~626mA / 공급 ~800mA
    ['INA226 전류', latest?.ina_current_ma, 'mA'],
  ];

  return (
    <div>
      {rows.map(([label, value, unit]) => (
        <div className="kv" key={label}>
          <span className="k">{label}</span>
          {value === null || value === undefined ? (
            <span className="v none">—</span>
          ) : (
            <span className="v">
              {value.toFixed(3)} {unit}
            </span>
          )}
        </div>
      ))}
      <div style={{ color: 'var(--muted)', fontSize: 11, marginTop: 10 }}>
        INA226 미장착 시 「—」로 표시됩니다.
      </div>
    </div>
  );
}
