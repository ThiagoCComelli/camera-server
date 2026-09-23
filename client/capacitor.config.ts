import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.thiagocomelli.cameraserver",
  appName: "Camera Server",
  webDir: "build/client",
  server: {
    // The camera server speaks plain HTTP, so the app is served over http too:
    // an https page would have its requests to it blocked as mixed content.
    androidScheme: "http",
    cleartext: true,
  },
};

export default config;
