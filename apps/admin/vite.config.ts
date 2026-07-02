import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the admin SPA calls `/api/*`; Vite proxies that to the local API on
// :8000 (strip the `/api` prefix). In production nginx performs the same proxy on
// admin.coruscant.com, so application code always talks to a same-origin `/api` — the
// exact-origin access model appropriate for a separate internal admin domain. A
// distinct dev port (5174) lets the console (5173) and admin run side by side.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
