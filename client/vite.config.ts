import { reactRouter } from "@react-router/dev/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [reactRouter()],
  resolve: {
    tsconfigPaths: true,
  },
  server: {
    proxy: {
      "/live": "http://localhost:49152",
      "/api": "http://localhost:49152",
    },
  },
});
