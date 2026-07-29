import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 콘솔은 백엔드의 /console 경로에 마운트된다 (app/main.py).
// base를 안 주면 자산 경로가 /assets/... 로 나가 404 → 흰 화면이 된다.
// 로컬 dev 서버(5180)는 루트로 뜨므로 개발 시에는 '/'를 쓴다.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? (process.env.VITE_BASE ?? '/console/') : '/',
  plugins: [react()],
}));
