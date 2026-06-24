import { useEffect, useRef } from 'react';
import { getWsUrl, isMockMode } from '../config/env';
import { useAuthStore } from '../store/authStore';
import { useDashboardStore } from '../store/dashboardStore';
import type { DashboardData } from '../types';

function parseWsMessage(raw: string): Partial<DashboardData> | null {
  try {
    const data = JSON.parse(raw) as Record<string, unknown>;
    if (data.payload && typeof data.payload === 'object') {
      return data.payload as Partial<DashboardData>;
    }
    if ('grid_current' in data || 'peak_active' in data) {
      return data as Partial<DashboardData>;
    }
    if (data.type === 'dashboard:update' && data.data) {
      return data.data as Partial<DashboardData>;
    }
    if (data.type === 'peak:alert') {
      return { ...(data.data as Partial<DashboardData>), peak_active: true };
    }
    return null;
  } catch {
    return null;
  }
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const setWsConnected = useDashboardStore((s) => s.setWsConnected);
  const mergeLiveData = useDashboardStore((s) => s.mergeLiveData);
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    if (isMockMode()) {
      setWsConnected(false);
      const interval = setInterval(() => {
        mergeLiveData({
          grid_current: 18.4 + (Math.random() - 0.5) * 0.4,
          ess_soc: 72 + (Math.random() - 0.5) * 0.2,
        });
      }, 5000);
      return () => clearInterval(interval);
    }

    const url = new URL(getWsUrl());
    if (token) {
      url.searchParams.set('token', token);
    }

    const ws = new WebSocket(url.toString());
    wsRef.current = ws;

    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);

    ws.onmessage = (event) => {
      const patch = parseWsMessage(event.data as string);
      if (patch) mergeLiveData(patch);
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [mergeLiveData, setWsConnected, token]);
}
