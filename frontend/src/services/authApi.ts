import type { LoginResponse, User } from '../types';
import { isMockMode } from '../config/env';
import { apiPaths } from '../config/apiPaths';
import { api } from './api';

// Backend response wrapper type
interface BackendResponse<T> {
  success: boolean;
  data: T;
}

// Backend auth data type (without user for now - we'll create a dummy user)
interface BackendAuthData {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  if (isMockMode()) {
    await new Promise((r) => setTimeout(r, 400));
    return {
      access_token: 'mock-jwt-token',
      user: { id: '1', email, name: 'Admin' },
    };
  }
  const { data } = await api.post<BackendResponse<BackendAuthData>>(apiPaths.authLogin, { email, password });
  console.log('📡 Backend login response:', data);
  
  // Extract access_token from nested data.data
  const accessToken = data.data.access_token;
  // Create a dummy user since backend doesn't return user data in this response
  const user: User = {
    id: '1',
    email,
    name: email.split('@')[0],
  };
  
  return {
    access_token: accessToken,
    user,
  };
}
