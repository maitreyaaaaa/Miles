import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
  },
  build: {
    rollupOptions: {
      input: {
        app: "index.html",
        ...(loadEnv(mode, ".", "VITE_").VITE_GOOGLE_MEET_ENABLED === "true" ? { meetingBridge: "meeting-bridge.html" } : {}),
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
}));
