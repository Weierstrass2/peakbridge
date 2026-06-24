export const isMockMode = (): boolean =>
  import.meta.env.VITE_USE_MOCK !== 'false';

export const BUILDING_ID =
  import.meta.env.VITE_BUILDING_ID || 'building-A';

export const getApiBaseUrl = (): string =>
  import.meta.env.REACT_APP_API_URL ||
  import.meta.env.VITE_API_URL ||
  'http://localhost:8000';

/** ws://host/api/v1/ws/{building_id} */
export const getWsUrl = (): string => {
  const path = `/api/v1/ws/${BUILDING_ID}`;

  if (import.meta.env.VITE_WS_URL) {
    const base = import.meta.env.VITE_WS_URL.replace(/\/$/, '').replace(/^http/, 'ws');
    return `${base}${path}`;
  }

  const httpBase = getApiBaseUrl().replace(/\/$/, '');
  return `${httpBase.replace(/^http/, 'ws')}${path}`;
};
