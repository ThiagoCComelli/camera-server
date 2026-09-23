import { Capacitor } from "@capacitor/core";

const isLocalHostname = (hostname: string) =>
  /^(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})$/.test(hostname);

export function isRemote() {
  return (
    Capacitor.isNativePlatform() || !isLocalHostname(window.location.hostname)
  );
}

export const getServerAddress = () =>
  localStorage.getItem("serverAddress") ?? "";
export const getToken = () => localStorage.getItem("token") ?? "";

function serverOrigin() {
  const address = getServerAddress().trim().replace(/\/+$/, "");
  if (!address) return "";
  return /^https?:\/\//.test(address) ? address : `http://${address}`;
}

export function apiUrl(path: string) {
  if (!isRemote()) return path;

  const url = new URL(path, serverOrigin() || window.location.origin);
  const token = getToken();
  if (token) url.searchParams.set("token", token);
  return url.toString();
}
