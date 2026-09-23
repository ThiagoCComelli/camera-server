import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.thiagocomelli.cameraserver",
  appName: "Camera Server",
  webDir: "build/client",
  server: {
    androidScheme: "http",
    cleartext: true,
  },
};

export default config;
