import { reactRouter } from "@react-router/dev/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [reactRouter()],
  resolve: {
    tsconfigPaths: true,
  },
  server: {
    proxy: {
      "/live": { target: "http://localhost:49152", ws: true },
      "/api": "http://localhost:49152",
    },
  },
});
