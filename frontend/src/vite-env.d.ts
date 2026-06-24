/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCK: string;
  readonly VITE_API_URL: string;
  readonly REACT_APP_API_URL: string;
  readonly VITE_WS_URL: string;
  readonly VITE_BUILDING_ID: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
