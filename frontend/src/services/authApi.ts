import type { LoginResponse } from '../types';
import { isMockMode } from '../config/env';
import { apiPaths } from '../config/apiPaths';
import { api } from './api';

export async function login(email: string, password: string): Promise<LoginResponse> {
  if (isMockMode()) {
    await new Promise((r) => setTimeout(r, 400));
    return {
      access_token: 'mock-jwt-token',
      user: { id: '1', email, name: 'Admin' },
    };
  }
  const { data } = await api.post<LoginResponse>(apiPaths.authLogin, { email, password });
  return data;
}
