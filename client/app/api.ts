import { Capacitor } from "@capacitor/core";

export const isApp = () => Capacitor.isNativePlatform();

export const getServerAddress = () =>
  localStorage.getItem("serverAddress") ?? "";
export const getToken = () => localStorage.getItem("token") ?? "";

export function apiUrl(path: string) {
  const address = isApp() ? getServerAddress().trim().replace(/\/+$/, "") : "";
  const token = getToken();
  if (!address && !token) return path;

  const origin = !address
    ? window.location.origin
    : /^https?:\/\//.test(address)
      ? address
      : `http://${address}`;
  const url = new URL(path, origin);
  if (token) url.searchParams.set("token", token);
  return url.toString();
}
