import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 서버(8010)가 dist를 '/'에 마운트하므로 base는 상대경로로 둔다.
export default defineConfig({
  base: './',
  plugins: [react()],
});
