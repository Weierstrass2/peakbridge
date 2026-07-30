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

/** 하드웨어 절체 임계(A) 설정 요청. 브리지가 폴링해 게이트웨이 config→MQTT로 XIAO에 전파. */
export async function setHwThreshold(high: number): Promise<void> {
  await api.post(apiPaths.hwThreshold(), { threshold_high_a: high });
}

/** AI 학습 기반 절체 임계 — 경제-물리 산출값 + 모드 상태. */
export interface AiThreshold {
  enabled: boolean;
  grid_current: number;
  computed_a: number; // 산출된 절체 임계(A)
  base_a: number; // 산출 기준부하
  rate_period: string; // 요금 구간(최대부하/중간부하/경부하)
  rate_factor: number;
  soc: number;
  soc_factor: number;
}

export async function getAiThreshold(): Promise<AiThreshold> {
  const { data } = await api.get<BackendResponse<AiThreshold>>(apiPaths.aiThreshold());
  return data.data;
}

/** AI 절체 임계 모드 on/off (관리자 인증). on이면 프론트가 산출값을 hw-threshold로 자동 적용. */
export async function setAiThresholdMode(enabled: boolean): Promise<void> {
  await api.post(apiPaths.aiThreshold(), { enabled });
}
