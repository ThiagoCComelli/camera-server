import { useEffect, useState } from "react";

export type Entry =
  | { type: "dir"; name: string; path: string; count: number }
  | {
      type: "file";
      name: string;
      path: string;
      startedAt: string;
      duration: number | null;
    };

const encodePath = (path: string) =>
  path.split("/").map(encodeURIComponent).join("/");

export const folderUrl = (path: string) =>
  path ? `/directory/${encodePath(path)}` : "/directory";

export const mediaUrl = (path: string) => `/api/media/${encodePath(path)}`;

const pad = (n: number) => String(n).padStart(2, "0");

export function formatDuration(seconds: number | null) {
  if (seconds === null) return "—";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "medium",
  });
}

/** The entries of one folder: `entries` is null while loading, `error` when it failed. */
export function useListing(path: string) {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setEntries(null);
    setError(null);

    fetch(`/api/files?path=${encodeURIComponent(path)}`, {
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Could not load this folder (HTTP ${res.status})`);
        return res.json() as Promise<{ entries: Entry[] }>;
      })
      .then((data) => setEntries(data.entries))
      .catch((err: Error) => {
        if (err.name !== "AbortError") setError(err.message);
      });

    return () => controller.abort();
  }, [path]);

  return { entries, error };
}
