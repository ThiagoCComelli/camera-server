import { useEffect, useState } from "react";

export type FeedStatus = "loading" | "live" | "offline";

const RETRY_MS = 3000;
const STALL_MS = 8000;

function indexOfMarker(buf: Uint8Array, marker: number, from: number) {
  for (let i = from; i < buf.length - 1; i++) {
    if (buf[i] === 0xff && buf[i + 1] === marker) return i;
  }
  return -1;
}

/**
 * Splits a multipart/x-mixed-replace stream into JPEG frames by looking for the
 * start (FF D8) and end (FF D9) markers, so the part headers never need parsing.
 */
export function createFrameParser(onFrame: (jpeg: Uint8Array<ArrayBuffer>) => void) {
  let buf: Uint8Array = new Uint8Array(0);

  return (chunk: Uint8Array) => {
    if (buf.length) {
      const joined = new Uint8Array(buf.length + chunk.length);
      joined.set(buf);
      joined.set(chunk, buf.length);
      buf = joined;
    } else {
      buf = chunk;
    }

    for (;;) {
      const start = indexOfMarker(buf, 0xd8, 0);
      if (start < 0) {
        buf = buf.subarray(Math.max(0, buf.length - 1)); // a marker may be split
        return;
      }
      const end = indexOfMarker(buf, 0xd9, start + 2);
      if (end < 0) {
        buf = buf.subarray(start);
        return;
      }
      onFrame(buf.slice(start, end + 2));
      buf = buf.subarray(end + 2);
    }
  };
}

/**
 * Follows an MJPEG endpoint and exposes the newest frame as an object URL.
 * An <img> pointed straight at a dead stream just freezes without any event, so
 * this owns the connection and reconnects when it ends, fails or stops sending.
 */
export function useMjpeg(url: string) {
  const [src, setSrc] = useState<string | null>(null);
  const [status, setStatus] = useState<FeedStatus>("loading");

  useEffect(() => {
    let cancelled = false;
    let controller: AbortController | undefined;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let stallTimer: ReturnType<typeof setTimeout> | undefined;
    let current: string | null = null;

    const show = (jpeg: Uint8Array<ArrayBuffer>) => {
      const next = URL.createObjectURL(new Blob([jpeg], { type: "image/jpeg" }));
      setSrc(next);
      if (current) URL.revokeObjectURL(current);
      current = next;
    };

    const clear = () => {
      setSrc(null);
      if (current) URL.revokeObjectURL(current);
      current = null;
    };

    const watchForStall = () => {
      clearTimeout(stallTimer);
      stallTimer = setTimeout(() => controller?.abort(), STALL_MS);
    };

    const connect = async () => {
      controller = new AbortController();
      watchForStall();
      const parse = createFrameParser((jpeg) => {
        show(jpeg);
        setStatus("live");
        watchForStall();
      });

      try {
        const res = await fetch(url, {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
        const reader = res.body.getReader();
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          parse(value);
        }
      } catch {
        // fall through: a failed, dropped or stalled stream all reconnect
      }

      clearTimeout(stallTimer);
      if (cancelled) return;
      clear();
      setStatus("offline");
      retryTimer = setTimeout(connect, RETRY_MS);
    };

    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      clearTimeout(stallTimer);
      controller?.abort();
      clear();
    };
  }, [url]);

  return { src, status };
}
