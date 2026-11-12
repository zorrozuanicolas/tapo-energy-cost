import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // One origin in development: the browser calls /api on the Vite server, which forwards it to the backend.
    proxy: { "/api": "http://localhost:8000" },
  },
});
