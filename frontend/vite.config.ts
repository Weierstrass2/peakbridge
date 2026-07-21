import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  // 배포 시 VITE_BASE=/app/ 로 서브경로 서빙, 로컬 개발은 '/'
  base: process.env.VITE_BASE || '/',
  plugins: [react(), tailwindcss()],
  envPrefix: ['VITE_', 'REACT_APP_'],
});
