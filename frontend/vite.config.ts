/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // In docker compose the backend is reachable by service name; override with
    // VITE_API_TARGET=http://localhost:8000 when running vite outside compose.
    proxy: { "/api": process.env.VITE_API_TARGET || "http://backend:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
