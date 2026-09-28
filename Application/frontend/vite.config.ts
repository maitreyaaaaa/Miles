import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
  },
  build: {
    rollupOptions: {
      input: {
        app: "index.html",
        meetingBridge: "meeting-bridge.html",
      },
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) return "vendor-react";
          if (id.includes("/node_modules/motion/") || id.includes("\\node_modules\\motion\\")) return "vendor-motion";
          if (id.includes("/node_modules/@supabase/") || id.includes("\\node_modules\\@supabase\\")) return "vendor-supabase";
        },
      },
    },
  },
});
