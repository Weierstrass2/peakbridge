import axios from 'axios';
import { getApiBaseUrl } from '../config/env';
import { useAuthStore } from '../store/authStore';

export const api = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 10_000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  const { refreshToken, setToken, logout } = useAuthStore.getState();
  if (!refreshToken) {
    logout();
    return null;
  }
  try {
    const res = await axios.post(
      `${getApiBaseUrl()}/api/v1/auth/refresh`,
      { refresh_token: refreshToken },
    );
    const newToken: string | undefined = res.data?.data?.access_token;
    if (!newToken) throw new Error('no token');
    setToken(newToken);
    return newToken;
  } catch {
    logout();
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config ?? {};
    if (
      error.response?.status === 401 &&
      !original._retried &&
      !String(original.url ?? '').includes('/auth/')
    ) {
      original._retried = true;
      refreshing = refreshing ?? tryRefresh();
      const newToken = await refreshing;
      refreshing = null;
      if (newToken) {
        original.headers = { ...original.headers, Authorization: `Bearer ${newToken}` };
        return api.request(original);
      }
    }
    return Promise.reject(error);
  },
);
