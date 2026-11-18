import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // One origin in development: the browser calls /api on the Vite server, which forwards it to the backend.
    proxy: { "/api": "http://localhost:8000" },
  },
  test: {
    // Pure logic (API client, dates, formatting) runs in Node. Component tests (.test.tsx) opt in to the
    // browser-like environment with a `// @vitest-environment jsdom` comment on their first line.
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test-setup.ts"],
  },
});
