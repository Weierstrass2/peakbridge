import type { ChartPoint, DashboardData, EventLogEntry } from '../types';
import { isMockMode } from '../config/env';
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
  console.log('📡 Backend dashboard response:', data);
  return data.data;
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

  // Fallback to mock chart data since backend doesn't have sensor history endpoint yet
  return mockFetch([...mockChartHistory]);
}

export async function fetchEvents(): Promise<EventLogEntry[]> {
  if (isMockMode()) {
    return mockFetch([...mockEvents]);
  }

  try {
    const alerts = await fetchAlerts();
    return alerts.map(alertToEvent);
  } catch {
    // If alerts endpoint fails, use mock events
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
