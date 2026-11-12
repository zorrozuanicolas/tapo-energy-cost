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
    // The logic tested so far (API client, dates, formatting) does not touch the DOM.
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
