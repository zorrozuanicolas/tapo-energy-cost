import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // One origin in development: the browser calls /api on the Vite server, which forwards it to the backend.
    proxy: { "/api": "http://localhost:8000" },
  },
});
