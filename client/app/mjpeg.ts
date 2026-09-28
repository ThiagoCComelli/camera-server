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
 * Behind a proxy a frame arrives in many small chunks, so bytes are appended to a
 * growable buffer and the end-marker search resumes where it stopped instead of
 * re-copying and re-scanning the whole partial frame on every chunk.
 */
export function createFrameParser(onFrame: (jpeg: Uint8Array<ArrayBuffer>) => void) {
  let buf = new Uint8Array(1 << 16);
  let len = 0;
  let start = -1; // offset of the current frame's FF D8, if found
  let scanned = 0; // bytes already searched for the next marker

  const append = (chunk: Uint8Array) => {
    if (len + chunk.length > buf.length) {
      let size = buf.length;
      while (size < len + chunk.length) size *= 2;
      const grown = new Uint8Array(size);
      grown.set(buf.subarray(0, len));
      buf = grown;
    }
    buf.set(chunk, len);
    len += chunk.length;
  };

  return (chunk: Uint8Array) => {
    append(chunk);

    for (;;) {
      const view = buf.subarray(0, len);
      if (start < 0) {
        start = indexOfMarker(view, 0xd8, scanned);
        if (start < 0) {
          scanned = Math.max(0, len - 1); // a marker may be split
          return;
        }
        scanned = start + 2;
      }
      const end = indexOfMarker(view, 0xd9, scanned);
      if (end < 0) {
        scanned = Math.max(start + 2, len - 1);
        return;
      }
      onFrame(buf.slice(start, end + 2));
      buf.copyWithin(0, end + 2, len);
      len -= end + 2;
      start = -1;
      scanned = 0;
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
          watchForStall(); // a slow link still counts as alive while bytes flow
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
