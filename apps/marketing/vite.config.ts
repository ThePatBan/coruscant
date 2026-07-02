import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The marketing site is fully static — no backend of its own. Every call to action
// links out to the console (a different origin), so there is no dev API proxy here. A
// distinct dev port (5175) lets it run alongside the console (5173) and admin (5174).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
  },
});
