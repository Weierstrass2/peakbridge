export type ChargerStatus = 'charging' | 'idle' | 'error' | 'paused';

export interface Charger {
  device_id: string;
  current: number;
  status: ChargerStatus;
}

export interface ForecastPoint {
  time: string;
  predicted: number;
  will_exceed: boolean;
}

export interface DashboardData {
  grid_current: number;
  ess_soc: number;
  ess_discharge: number;
  peak_active: boolean;
  peak_threshold: number;
  peak_reduction_pct: number;
  chargers: Charger[];
  forecast: ForecastPoint[];
  today_saved_won: number;
  month_saved_won: number;
  co2_reduced_kg: number;
}

export interface ChartPoint {
  time: string;
  grid_current: number;
  ess_discharge: number;
  charger_total: number;
}

export interface EventLogEntry {
  id: string;
  timestamp: string;
  level: 'info' | 'warning' | 'success';
  message: string;
}

export interface SensorReading {
  sensor_id: string;
  type: string;
  value: number;
  unit: string;
  timestamp: string;
}

export interface ReportSummary {
  period: string;
  total_saved_won: number;
  peak_events: number;
  co2_reduced_kg: number;
  avg_grid_current: number;
}

export interface AlertItem {
  id: string;
  type: 'peak' | 'ess_low' | 'charger_fault';
  message: string;
  timestamp: string;
  acknowledged: boolean;
}

export interface User {
  id: string;
  email: string;
  name: string;
}

export interface LoginResponse {
  access_token: string;
  user: User;
}

export interface ControlAction {
  action: 'pause_charger' | 'resume_charger' | 'set_threshold';
  device_id?: string;
  value?: number;
}
