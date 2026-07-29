import { BUILDING_ID } from './env';

const V1 = '/api/v1';

export const apiPaths = {
  authLogin: `${V1}/auth/login`,
  dashboard: (buildingId = BUILDING_ID) => `${V1}/dashboard/${buildingId}`,
  sensorHistory: (deviceId: string) => `${V1}/sensors/${deviceId}/history`,
  controlRelay: (buildingId = BUILDING_ID) => `${V1}/control/${buildingId}/relay`,
  reportsSavings: (buildingId = BUILDING_ID) => `${V1}/reports/${buildingId}/savings`,
  alerts: (buildingId = BUILDING_ID) => `${V1}/alerts/${buildingId}`,
  // 차주 화면(/drive)에서 등록된 충전 세션 — 관제 운영자 조회용
  driveSessions: `${V1}/drive/sessions`,
  driveFlexibility: `${V1}/drive/flexibility`,
} as const;

/** 차트용 기본 센서 device_id (백엔드 device_id와 맞춰 변경) */
export const SENSOR_DEVICE_IDS = {
  grid: 'GRID-01',
  ess: 'ESS-01',
  chargerTotal: 'CHARGER-TOTAL',
} as const;
