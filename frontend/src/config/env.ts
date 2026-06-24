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
    const base = import.meta.env.VITE_WS_URL.replace(/\/$/, '');
    // If base already starts with ws:// or wss://, use it directly
    if (base.startsWith('ws://') || base.startsWith('wss://')) {
      return `${base}${path}`;
    }
    // Otherwise, convert http to ws
    return `${base.replace(/^http/, 'ws')}${path}`;
  }

  const httpBase = getApiBaseUrl().replace(/\/$/, '');
  return `${httpBase.replace(/^http/, 'ws')}${path}`;
};
