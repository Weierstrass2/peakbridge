import { create } from 'zustand';
import type { DashboardData } from '../types';

interface DashboardState {
  liveData: Partial<DashboardData> | null;
  wsConnected: boolean;
  lastUpdated: string | null;
  setLiveData: (data: Partial<DashboardData>) => void;
  setWsConnected: (connected: boolean) => void;
  mergeLiveData: (patch: Partial<DashboardData>) => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  liveData: null,
  wsConnected: false,
  lastUpdated: null,
  setLiveData: (data) =>
    set({ liveData: data, lastUpdated: new Date().toISOString() }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  mergeLiveData: (patch) =>
    set((state) => ({
      liveData: { ...state.liveData, ...patch },
      lastUpdated: new Date().toISOString(),
    })),
}));
