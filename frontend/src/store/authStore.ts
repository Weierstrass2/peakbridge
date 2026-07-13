import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '../types';

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  setAuth: (token: string, user: User, refreshToken?: string | null) => void;
  setToken: (token: string) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      refreshToken: null,
      user: null,
      setAuth: (token, user, refreshToken = null) => set({ token, user, refreshToken }),
      setToken: (token) => set({ token }),
      logout: () => set({ token: null, user: null, refreshToken: null }),
      isAuthenticated: () => !!get().token,
    }),
    { name: 'peakbridge-auth' },
  ),
);
