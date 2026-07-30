// '하드웨어 실측' 탭 전용 API — 클라우드 dashboard 응답에서 실기(ESS) 필드만 읽는다.
// 데이터 출처: 로컬 게이트웨이(hardware/server) 브리지 → 백엔드 ess-runtime 사이드채널.
import { apiPaths } from '../config/apiPaths';
import { api } from './api';

/** 브리지가 올린 실시간 릴레이/계측 상태 (없으면 하드웨어 미연결 → null). */
export interface HardwareStatus {
  grid_current: number;
  ess_soc: number;
  ess_remain_hours: number | null;
  ess_battery_temp_c: number | null;
  ess_inverter_temp_c: number | null;
  thermal_lock: boolean | null;
  relay_state: 'NC' | 'NO' | null;
  ess_ina_current_ma: number | null;
  hw_threshold_high_a: number | null;
  hold_remaining_s: number | null;
  peak_threshold: number;
  last_updated: string;
}

interface BackendResponse<T> {
  success: boolean;
  data: T;
}

export async function fetchHardwareStatus(): Promise<HardwareStatus> {
  const { data } = await api.get<BackendResponse<HardwareStatus>>(apiPaths.dashboard());
  return data.data;
}
