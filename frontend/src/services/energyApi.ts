import { api } from './api';

const V1 = '/api/v1';

/** 백엔드 응답이 { success, data } 래핑일 수도, 원본 dict일 수도 있어 둘 다 처리 */
export function unwrap<T>(payload: unknown): T {
  const p = payload as { data?: unknown; success?: boolean };
  if (p && typeof p === 'object' && 'success' in p && 'data' in p) {
    return p.data as T;
  }
  return payload as T;
}

export const energyApi = {
  getCurrentRate: () => api.get(`${V1}/energy/current-rate`),

  getRecommendation: (buildingId: string) =>
    api.get(`${V1}/energy/recommendation/${buildingId}`),

  getArbitrage: (buildingId: string) =>
    api.get(`${V1}/energy/arbitrage/${buildingId}`),

  getSchedule: (buildingId: string) =>
    api.get(`${V1}/energy/schedule/${buildingId}`),

  /** PPO 기반 AI 권고 (백엔드 준비 시 자동 사용, 없으면 규칙 기반으로 폴백) */
  getAiRecommend: (buildingId: string) =>
    api.get(`${V1}/ai/recommend/${buildingId}`),

  /** AI 시나리오 발동 상태 */
  getAiScenarios: (buildingId: string) =>
    api.get(`${V1}/ai/scenarios/${buildingId}`),
};
