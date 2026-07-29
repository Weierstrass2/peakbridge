/** 백엔드 API 클라이언트 — 차주 화면(/drive) 전용 경량 fetch 래퍼. */

const BASE =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ??
  'https://peakbridge-production.up.railway.app';

const V1 = `${BASE}/api/v1`;

function unwrap<T>(payload: unknown): T {
  const p = payload as { success?: boolean; data?: unknown };
  if (p && typeof p === 'object' && 'success' in p && 'data' in p) return p.data as T;
  return payload as T;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${V1}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return unwrap<T>(await res.json());
}

export type ChargeMode = 'eco' | 'now';

export interface DriveSession {
  code: string;
  household: string;
  building_id: string;
  need_kwh: number;
  depart: string;
  depart_hour: number | null;
  mode: ChargeMode;
  mode_label: string;
  status: 'active' | 'cancelled' | 'done';
  is_flexible: boolean;
  created_at: string;
  error?: string;
}

export interface Flexibility {
  building_id: string;
  flex_kwh: number;
  flex_session_count: number;
  immediate_kwh: number;
  immediate_session_count: number;
  updated_at: string;
}

export const api = {
  createSession(body: {
    household: string;
    need_kwh: number;
    depart: string;
    mode: ChargeMode;
    building_id?: string;
  }) {
    return req<DriveSession>('/drive/session', {
      method: 'POST',
      body: JSON.stringify({ building_id: 'building-A', ...body }),
    });
  },

  getSession(code: string) {
    return req<DriveSession>(`/drive/session/${encodeURIComponent(code)}`);
  },

  cancelSession(code: string) {
    return req<DriveSession>(`/drive/session/${encodeURIComponent(code)}/cancel`, {
      method: 'POST',
    });
  },

  flexibility(buildingId = 'building-A') {
    return req<Flexibility>(`/drive/flexibility?building_id=${encodeURIComponent(buildingId)}`);
  },
};
