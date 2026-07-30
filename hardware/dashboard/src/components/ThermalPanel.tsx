import type { Telemetry } from '../lib/api';

// 온도 차단 기준(펌웨어와 동일 — 표시용). 판정 자체는 메인 보드가 로컬로 한다.
const TRIP_C = 50;
const RELEASE_C = 43;

/**
 * Sense 보드(BME280 x2) 온도 + 메인 보드의 열 차단(thermal_lock) 상태.
 * 온도는 메인 보드 텔레메트리에 실려 오므로(별도 전선 없음), 값이 없으면 "—".
 */
export function ThermalPanel({ latest }: { latest: Telemetry | null }) {
  const bt = latest?.battery_temp_c;
  const it = latest?.inverter_temp_c;
  const locked = latest?.thermal_lock === true;
  const temps = [bt, it].filter((v): v is number => typeof v === 'number');
  const hottest = temps.length ? Math.max(...temps) : null;

  const rows: [string, number | null | undefined][] = [
    ['배터리 옆 온도', bt],
    ['인버터 옆 온도', it],
  ];

  return (
    <div>
      <div
        style={{
          padding: '8px 10px',
          borderRadius: 6,
          marginBottom: 10,
          fontWeight: 600,
          background: locked ? 'rgba(229,72,77,0.12)' : 'rgba(46,189,133,0.10)',
          color: locked ? '#E5484D' : '#2EBD85',
          border: `1px solid ${locked ? 'rgba(229,72,77,0.4)' : 'rgba(46,189,133,0.3)'}`,
        }}
      >
        {locked ? '⚠ 열 차단 발동 — ESS 방전 정지(과열, 한전 고정)' : '정상 (열 차단 대기)'}
      </div>

      {rows.map(([label, value]) => (
        <div className="kv" key={label}>
          <span className="k">{label}</span>
          {value === null || value === undefined ? (
            <span className="v none">—</span>
          ) : (
            <span className="v" style={{ color: value >= TRIP_C ? '#E5484D' : undefined }}>
              {value.toFixed(1)} °C
            </span>
          )}
        </div>
      ))}

      <div style={{ color: 'var(--muted)', fontSize: 11, marginTop: 10 }}>
        트립 {TRIP_C}°C / 해제 {RELEASE_C}°C · 둘 중 더 뜨거운 값으로 판정 (히스테리시스)
        {hottest !== null && ` · 현재 최고 ${hottest.toFixed(1)}°C`}
        <br />
        Sense 보드(BME280) 미연결 시 「—」로 표시됩니다.
      </div>
    </div>
  );
}
