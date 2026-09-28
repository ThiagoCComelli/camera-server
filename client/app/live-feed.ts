import { useEffect, useState } from "react";

export type FeedStatus = "loading" | "live" | "offline";

const RETRY_MS = 3000;
const STALL_MS = 8000; // the server holds a request up to 5 s waiting for a frame

/**
 * Shows the camera by repeatedly fetching its newest frame as a single JPEG.
 *
 * A continuous MJPEG stream lags behind a proxy like Cloudflare: the server
 * pushes frames faster than the link drains them and they queue up in between,
 * so the delay only grows. Here the next frame is requested only once the last
 * one has arrived and decoded, so nothing queues: a slow link or device gets a
 * lower frame rate, but every frame shown is the most recent one.
 */
export function useLiveFeed(url: string) {
  const [src, setSrc] = useState<string | null>(null);
  const [status, setStatus] = useState<FeedStatus>("loading");

  useEffect(() => {
    let cancelled = false;
    let controller: AbortController | undefined;
    let wake: (() => void) | undefined;
    let current: string | null = null;
    let seq = 0;

    const pause = (ms?: number) =>
      new Promise<void>((resolve) => {
        wake = resolve;
        if (ms !== undefined) setTimeout(resolve, ms);
      });

    const onVisibility = () => {
      if (!document.hidden) wake?.();
    };
    document.addEventListener("visibilitychange", onVisibility);

    const fetchFrame = async () => {
      const frameUrl = new URL(url, window.location.href);
      frameUrl.searchParams.set("after", String(seq));
      controller = new AbortController();
      const stall = setTimeout(() => controller?.abort(), STALL_MS);
      try {
        const res = await fetch(frameUrl, {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        return { blob, seq: Number(res.headers.get("X-Frame-Seq")) || 0 };
      } finally {
        clearTimeout(stall);
      }
    };

    const show = async (blob: Blob) => {
      const next = URL.createObjectURL(blob);
      try {
        // decode off-screen first, so a slow device also slows the requests
        const img = new Image();
        img.src = next;
        await img.decode();
      } catch (error) {
        URL.revokeObjectURL(next);
        throw error;
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

    const run = async () => {
      while (!cancelled) {
        if (document.hidden) {
          await pause(); // no point downloading frames nobody sees
          continue;
        }
        try {
          const frame = await fetchFrame();
          if (cancelled) return;
          seq = frame.seq;
          await show(frame.blob);
          setStatus("live");
        } catch {
          if (cancelled) return;
          clear();
          setStatus("offline");
          await pause(RETRY_MS);
        }
      }
    };

    run();

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      controller?.abort();
      wake?.();
      clear();
    };
  }, [url]);

  return { src, status };
}
