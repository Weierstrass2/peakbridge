import type { ChartPoint, DashboardData, EventLogEntry } from '../types';
import { isMockMode } from '../config/env';
import { apiPaths, SENSOR_DEVICE_IDS } from '../config/apiPaths';
import { mockChartHistory, mockDashboard, mockEvents, mockFetch } from '../mock/mockData';
import { api } from './api';
import type { DashboardResponse } from './mappers';
import { alertToEvent, mergeChartSeries } from './mappers';
import { fetchAlerts } from './reportApi';

export async function fetchDashboard(): Promise<DashboardData> {
  if (isMockMode()) {
    return mockFetch({ ...mockDashboard });
  }
  const { data } = await api.get<DashboardResponse>(apiPaths.dashboard());
  const { chart_history: _c, events: _e, ...dashboard } = data;
  return dashboard;
}

export async function fetchDashboardFull(): Promise<DashboardResponse> {
  if (isMockMode()) {
    return mockFetch({
      ...mockDashboard,
      chart_history: mockChartHistory,
      events: mockEvents,
    });
  }
  const { data } = await api.get<DashboardResponse>(apiPaths.dashboard());
  return data;
}

export async function fetchChartHistory(): Promise<ChartPoint[]> {
  if (isMockMode()) {
    return mockFetch([...mockChartHistory]);
  }

  const full = await fetchDashboardFull();
  if (full.chart_history?.length) {
    return full.chart_history;
  }

  const hours = 24;
  const [grid, ess, charger] = await Promise.all([
    api.get(apiPaths.sensorHistory(SENSOR_DEVICE_IDS.grid), { params: { hours } }),
    api.get(apiPaths.sensorHistory(SENSOR_DEVICE_IDS.ess), { params: { hours } }),
    api.get(apiPaths.sensorHistory(SENSOR_DEVICE_IDS.chargerTotal), { params: { hours } }),
  ]);

  return mergeChartSeries(grid.data, ess.data, charger.data);
}

export async function fetchEvents(): Promise<EventLogEntry[]> {
  if (isMockMode()) {
    return mockFetch([...mockEvents]);
  }

  const full = await fetchDashboardFull();
  if (full.events?.length) {
    return full.events;
  }

  const alerts = await fetchAlerts();
  return alerts.map(alertToEvent);
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
