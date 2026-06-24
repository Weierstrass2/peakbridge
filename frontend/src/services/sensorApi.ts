import type { SensorReading } from '../types';
import { isMockMode } from '../config/env';
import { apiPaths } from '../config/apiPaths';
import { mockFetch } from '../mock/mockData';
import { api } from './api';

const mockSensors: SensorReading[] = [
  { sensor_id: 'GRID-01', type: 'current', value: 18.4, unit: 'A', timestamp: new Date().toISOString() },
  { sensor_id: 'ESS-01', type: 'soc', value: 72, unit: '%', timestamp: new Date().toISOString() },
  { sensor_id: 'ESS-01', type: 'discharge', value: 5.2, unit: 'A', timestamp: new Date().toISOString() },
];

export async function fetchSensorHistory(deviceId: string, hours = 24): Promise<SensorReading[]> {
  if (isMockMode()) {
    return mockFetch([...mockSensors]);
  }
  const { data } = await api.get<SensorReading[]>(apiPaths.sensorHistory(deviceId), {
    params: { hours },
  });
  return data;
}
