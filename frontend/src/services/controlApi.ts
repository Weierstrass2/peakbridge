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
