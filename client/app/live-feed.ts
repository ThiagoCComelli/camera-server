import { useEffect, useState } from "react";

export type FeedStatus = "loading" | "live" | "offline";

const RETRY_MS = 3000;
const STALL_MS = 8000; // the server repeats the last frame every 5 s at worst

/**
 * Shows the camera from a WebSocket that carries one JPEG per message.
 *
 * A continuous MJPEG stream lags behind a proxy like Cloudflare: the server
 * pushes frames faster than the link drains them and they queue up in between,
 * so the delay only grows. Here the server sends the next frame only after this
 * side acknowledges the last one was decoded and shown, so nothing queues: a
 * slow link or device gets a lower frame rate, but every frame shown is the
 * most recent one.
 */
export function useLiveFeed(url: string) {
  const [src, setSrc] = useState<string | null>(null);
  const [status, setStatus] = useState<FeedStatus>("loading");

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | undefined;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let stallTimer: ReturnType<typeof setTimeout> | undefined;
    let current: string | null = null;

    const wsUrl = new URL(url, window.location.href);
    wsUrl.protocol = wsUrl.protocol === "https:" ? "wss:" : "ws:";

    const show = async (blob: Blob) => {
      const next = URL.createObjectURL(blob);
      try {
        // decode off-screen first, so a slow device also slows the frame rate
        const img = new Image();
        img.src = next;
        await img.decode();
      } catch {
        URL.revokeObjectURL(next);
        return;
      }
      if (cancelled) return URL.revokeObjectURL(next);
      setSrc(next);
      if (current) URL.revokeObjectURL(current);
      current = next;
    };

    const clear = () => {
      setSrc(null);
      if (current) URL.revokeObjectURL(current);
      current = null;
    };

    const watchForStall = (ws: WebSocket) => {
      clearTimeout(stallTimer);
      stallTimer = setTimeout(() => ws.close(), STALL_MS);
    };

    const connect = () => {
      // no point receiving frames nobody sees; visibilitychange reconnects
      if (document.hidden) return;
      const ws = new WebSocket(wsUrl);
      ws.binaryType = "blob";
      socket = ws;
      watchForStall(ws);

      ws.onmessage = async (event) => {
        watchForStall(ws);
        await show(event.data as Blob);
        if (cancelled || ws !== socket) return;
        setStatus("live");
        if (ws.readyState === WebSocket.OPEN) ws.send("next");
      };

      ws.onclose = () => {
        clearTimeout(stallTimer);
        if (cancelled || ws !== socket) return;
        socket = undefined;
        clear();
        setStatus("offline");
        retryTimer = setTimeout(connect, RETRY_MS);
      };
    };

    const onVisibility = () => {
      if (document.hidden) {
        clearTimeout(retryTimer);
        const ws = socket;
        socket = undefined; // closing on purpose: onclose must not retry
        clearTimeout(stallTimer);
        ws?.close();
      } else if (!socket) {
        clearTimeout(retryTimer);
        setStatus("loading");
        connect();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    connect();

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      clearTimeout(retryTimer);
      clearTimeout(stallTimer);
      socket?.close();
      clear();
    };
  }, [url]);

  return { src, status };
}
