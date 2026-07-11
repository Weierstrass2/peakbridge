import { api } from './api';
import { unwrap } from './energyApi';

const V1 = '/api/v1';

export interface VppBuilding {
  building_id: string;
  ess_capacity: number;
  current_soc: number;
  usable_kwh: number;
  available_kw: number;
  live?: boolean;
}

export interface VppPortfolio {
  total_capacity_kwh: number;
  available_flexibility_kw: number;
  building_count: number;
  buildings: VppBuilding[];
  note?: string;
}

export interface DrRevenue {
  reduction_kwh: number;
  smp_price: number;
  gross_revenue: number;
  peakbridge_fee: number;
  net_revenue: number;
  monthly_projection: number;
}

export interface ArbRevenue {
  charge_cost: number;
  discharge_savings: number;
  arbitrage: number;
  roi_percent: number;
  monthly_projection: number;
  charge_price?: number;
  discharge_price?: number;
}

export interface DrEvent {
  event_id: string;
  signal_type: string;
  value: number;
  label: string;
  action: string;
  discharge_percent?: number;
  issued_at: string;
}

export interface DrStatus {
  vtn: { role: string; online: boolean };
  ven: { role: string; state: string; registered: boolean };
  active_event: DrEvent | null;
}

export const vppApi = {
  getPortfolio: async () =>
    unwrap<VppPortfolio>((await api.get(`${V1}/vpp/portfolio`)).data),

  getDrRevenue: async () =>
    unwrap<DrRevenue>((await api.get(`${V1}/vpp/revenue/dr`)).data),

  getArbitrage: async () =>
    unwrap<ArbRevenue>((await api.get(`${V1}/vpp/revenue/arbitrage`)).data),

  getDrStatus: async () =>
    unwrap<DrStatus>((await api.get(`${V1}/dr/status`)).data),

  getDrHistory: async () =>
    unwrap<{ events: DrEvent[]; count: number }>(
      (await api.get(`${V1}/dr/history`, { params: { limit: 8 } })).data,
    ),

  issueDrEvent: async (signalType: string, value: number) =>
    unwrap<DrEvent>(
      (
        await api.post(`${V1}/dr/event`, {
          signal_type: signalType,
          value,
          building_id: 'building-A',
        })
      ).data,
    ),

  triggerScenario: async (scenario: string) =>
    unwrap<{ message: string; action: string; status: string }>(
      (
        await api.post(`${V1}/simulation/trigger`, {
          scenario,
          building_id: 'building-A',
        })
      ).data,
    ),
};
