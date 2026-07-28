import type { Telemetry } from '../lib/api';

interface Props {
  latest: Telemetry | null;
  stale: boolean; // 최신 텔레메트리가 10초 이상 끊긴 상태
}

export function RelayStateBanner({ latest, stale }: Props) {
  if (!latest || stale) {
    return (
      <div className="banner stale">
        <div>
          <div className="label">연결 대기</div>
          <div className="meta">
            {latest ? 'ESP32 텔레메트리 10초 이상 수신 없음' : '아직 수신된 텔레메트리가 없습니다'}
          </div>
        </div>
        <div className="value">—</div>
      </div>
    );
  }

  const isPeak = latest.relay_state === 'NO';

  return (
    <div className={`banner ${isPeak ? 'no' : 'nc'}`}>
      <div>
        <div className="label">{isPeak ? '피크 — ESS 공급 (NO)' : '평상시 — 한전 공급 (NC)'}</div>
        <div className="meta">
          I_high {latest.threshold_high_a}A · I_low {latest.threshold_low_a}A
          {latest.hold_remaining_s > 0 && ` · 최소 유지 ${latest.hold_remaining_s}초 남음`}
          {isPeak && latest.hold_remaining_s === 0 && ' · 유지시간 만료 (복귀 조건 대기)'}
        </div>
      </div>
      <div className="value">{latest.grid_current_a.toFixed(3)} A</div>
    </div>
  );
}
