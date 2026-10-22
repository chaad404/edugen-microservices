import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API calls go to the gateway started by docker compose (port 8080)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8080", changeOrigin: true } },
  },
});
