/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend URL when the API is on another origin (empty in development and behind one proxy). */
  readonly VITE_API_URL?: string;
  /** Time zone for "today" (default America/Montevideo). It must match the backend's TIMEZONE. */
  readonly VITE_TIMEZONE?: string;
  /** "true" in the demo build, which has no backend (`.env.demo`). */
  readonly VITE_DEMO?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
