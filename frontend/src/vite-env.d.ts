/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend URL when the API is on another origin (empty in development and behind one proxy). */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
