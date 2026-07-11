import type { ChartPoint, DashboardData, EventLogEntry } from '../types';
import { isMockMode } from '../config/env';
import type { SensorReading } from '../types';
import { apiPaths, SENSOR_DEVICE_IDS } from '../config/apiPaths';
import { mockChartHistory, mockDashboardData, mockEvents, mockFetch } from '../mock/mockData';
import { api } from './api';
import type { DashboardResponse } from './mappers';
import { alertToEvent, mergeChartSeries } from './mappers';
import { fetchAlerts } from './reportApi';

// Backend response wrapper type
interface BackendResponse<T> {
  success: boolean;
  data: T;
}

export async function fetchDashboard(): Promise<DashboardData> {
  if (isMockMode()) {
    return mockFetch({ ...mockDashboardData });
  }
  const { data } = await api.get<BackendResponse<DashboardData>>(apiPaths.dashboard());
  return data.data;
}

interface HistoryItem {
  time: string;
  avg_value: number;
  unit: string;
}

async function fetchDeviceHistory(deviceId: string): Promise<SensorReading[]> {
  const { data } = await api.get<BackendResponse<{ history: HistoryItem[] }>>(
    apiPaths.sensorHistory(deviceId),
    { params: { interval: '5min' } },
  );
  return (data.data.history ?? []).map((h) => ({
    sensor_id: deviceId,
    type: 'history',
    value: h.avg_value,
    unit: h.unit,
    timestamp: h.time,
  }));
}

export async function fetchDashboardFull(): Promise<DashboardResponse> {
  if (isMockMode()) {
    return mockFetch({
      ...mockDashboardData,
      chart_history: mockChartHistory,
      events: mockEvents,
    });
  }
  // Fallback to mock for chart and events since backend doesn't have them yet
  const dashboard = await fetchDashboard();
  return {
    ...dashboard,
    chart_history: mockChartHistory,
    events: mockEvents,
  };
}

export async function fetchChartHistory(): Promise<ChartPoint[]> {
  if (isMockMode()) {
    return mockFetch([...mockChartHistory]);
  }

  try {
    const [grid, ess, charger] = await Promise.all([
      fetchDeviceHistory(SENSOR_DEVICE_IDS.grid).catch(() => [] as SensorReading[]),
      fetchDeviceHistory(SENSOR_DEVICE_IDS.ess).catch(() => [] as SensorReading[]),
      fetchDeviceHistory(SENSOR_DEVICE_IDS.chargerTotal).catch(() => [] as SensorReading[]),
    ]);
    const merged = mergeChartSeries(grid, ess, charger);
    return merged.length > 0 ? merged : mockFetch([...mockChartHistory]);
  } catch {
    return mockFetch([...mockChartHistory]);
  }
}

export async function fetchEvents(): Promise<EventLogEntry[]> {
  if (isMockMode()) {
    return mockFetch([...mockEvents]);
  }

  try {
    const alerts = await fetchAlerts();
    return alerts.map(alertToEvent);
  } catch {
    return mockFetch([...mockEvents]);
  }
}

export async function sendControlAction(
  action: string,
  payload?: Record<string, unknown>,
): Promise<void> {
  if (isMockMode()) {
    await mockFetch(null, 300);
    return;
  }
  await api.post(apiPaths.controlRelay(), {
    action,
    ...payload,
  });
}
