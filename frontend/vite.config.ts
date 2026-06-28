import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the SPA calls `/api/*`; Vite proxies that to the local API on
// :8000 (strip the `/api` prefix). In production nginx performs the same proxy,
// so application code always talks to a same-origin `/api`.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
