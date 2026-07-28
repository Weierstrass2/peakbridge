// 하드웨어 데모 서버 API 클라이언트 (frontend-vpp 패턴)

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8010';

export interface Telemetry {
  id: number;
  device_id: string;
  timestamp: number; // ESP32 epoch (NTP 미동기 시 0)
  received_at: number; // 서버 UTC epoch — 정렬·표시 기준
  grid_current_a: number;
  relay_state: 'NC' | 'NO';
  threshold_high_a: number;
  threshold_low_a: number;
  hold_remaining_s: number;
  battery_voltage_v: number | null;
  ess_current_a: number | null;
  ess_power_w: number | null;
  ina_current_ma: number | null; // INA226 배터리→인버터 전류 (복귀 판단 센서)
}

export interface RelayEvent {
  id: number;
  device_id: string;
  from_state: 'NC' | 'NO';
  to_state: 'NC' | 'NO';
  timestamp: number;
  received_at: number;
  grid_current_a: number;
}

export interface Config {
  threshold_high_a: number;
  threshold_low_a: number;
  min_hold_s: number;
  ina_low_ma: number;
  updated_at: number;
}

export interface ConfigUpdate {
  threshold_high_a: number;
  threshold_low_a: number;
  min_hold_s: number;
  ina_low_ma?: number;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) {
    throw new ApiError(resp.status, await readDetail(resp));
  }
  return (await resp.json()) as T;
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await readDetail(resp));
  }
  return (await resp.json()) as T;
}

async function readDetail(resp: Response): Promise<string> {
  try {
    const data = await resp.json();
    if (typeof data?.detail === 'string') return data.detail;
    return JSON.stringify(data);
  } catch {
    return `요청 실패 (HTTP ${resp.status})`;
  }
}

export interface DeviceInfo {
  device_id: string;
  samples: number;
  last_seen: number;
}

const q = (device?: string) => (device ? `&device_id=${encodeURIComponent(device)}` : '');

export const hardwareApi = {
  devices: () => get<DeviceInfo[]>('/api/devices'),
  latest: (device?: string) => get<Telemetry>(`/api/latest?${device ? `device_id=${encodeURIComponent(device)}` : ''}`),
  history: (minutes = 10, device?: string) => get<Telemetry[]>(`/api/history?minutes=${minutes}${q(device)}`),
  events: (device?: string) => get<RelayEvent[]>(`/api/events?limit=100${q(device)}`),
  getConfig: () => get<Config>('/api/config'),
  putConfig: (body: ConfigUpdate) => put<Config>('/api/config', body),
};

// 설정 검증 — 서버 models.validate_config / 펌웨어와 동일 규칙
export function validateConfig(c: ConfigUpdate): string | null {
  if (!Number.isFinite(c.threshold_high_a) || !Number.isFinite(c.threshold_low_a) || !Number.isFinite(c.min_hold_s)) {
    return '모든 값을 숫자로 입력해 주세요.';
  }
  if (c.threshold_low_a <= 0) return '복귀 임계값(I_low)은 0보다 커야 합니다.';
  if (c.threshold_high_a <= c.threshold_low_a) return '절체 임계값(I_high)은 복귀 임계값(I_low)보다 커야 합니다.';
  if (c.min_hold_s < 5 || c.min_hold_s > 300) return '최소 유지시간은 5~300초 범위여야 합니다.';
  if (c.ina_low_ma !== undefined && (c.ina_low_ma < 50 || c.ina_low_ma > 8200)) {
    return 'INA226 복귀 기준은 50~8200mA 범위여야 합니다.';
  }
  return null;
}

export function formatTime(receivedAt: number): string {
  return new Date(receivedAt * 1000).toLocaleTimeString('ko-KR', { hour12: false });
}
