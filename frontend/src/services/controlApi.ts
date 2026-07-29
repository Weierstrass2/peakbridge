import { api } from './api';
import { BUILDING_ID } from '../config/env';

const V1 = '/api/v1';

interface Wrapped<T> { success: boolean; data: T; }

export interface ControlLogItem {
  id: string;
  action: string;
  triggered_by: string;
  device_id: string;
  ess_soc_before: number;
  created_at: string | null;
}

export const controlApi = {
  getLogs: async (): Promise<ControlLogItem[]> => {
    const { data } = await api.get<Wrapped<ControlLogItem[]>>(
      `${V1}/control/${BUILDING_ID}/logs`, { params: { limit: 20 } },
    );
    return data.data;
  },

  setThreshold: async (value: number): Promise<void> => {
    await api.put(`${V1}/control/${BUILDING_ID}/threshold`, { value });
  },

  // 시연용 가상 시각 설정 (KST 0~23시). null이면 실시간 복원
  setDemoTime: async (hour: number | null): Promise<void> => {
    await api.post(`${V1}/control/${BUILDING_ID}/demo-time`, { hour });
  },

  // ESS 잔량 수동 100% 리셋 — 클라우드 즉시 반영 + 하드웨어 쿨롱 카운터 리셋 전파
  resetEssSoc: async (): Promise<void> => {
    await api.post(`${V1}/control/${BUILDING_ID}/ess-soc-reset`, {});
  },

  // 강제 방전 모드 on/off — 부하 무관 릴레이 NO(ESS) 유지 / 자동 판단 복귀
  setForceDischarge: async (on: boolean): Promise<void> => {
    await api.post(`${V1}/control/${BUILDING_ID}/ess-force-discharge`, { on });
  },

  getAutoMode: async (): Promise<boolean> => {
    const { data } = await api.get<Wrapped<{ enabled: boolean }>>(
      `${V1}/control/${BUILDING_ID}/auto-mode`,
    );
    return data.data.enabled;
  },

  setAutoMode: async (enabled: boolean): Promise<void> => {
    await api.post(`${V1}/control/${BUILDING_ID}/auto-mode`, { enabled });
  },

  controlCharger: async (deviceId: string, action: 'pause' | 'resume'): Promise<void> => {
    await api.post(`${V1}/control/${BUILDING_ID}/charger/${deviceId}`, { action });
  },
};
