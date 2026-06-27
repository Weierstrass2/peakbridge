import api from './api';

export const energyApi = {
  getCurrentRate: () =>
    api.get('/energy/current-rate'),

  getRecommendation: (buildingId: string) =>
    api.get(`/energy/recommendation/${buildingId}`),

  getArbitrage: (buildingId: string) =>
    api.get(`/energy/arbitrage/${buildingId}`),

  getSchedule: (buildingId: string) =>
    api.get(`/energy/schedule/${buildingId}`),
};
