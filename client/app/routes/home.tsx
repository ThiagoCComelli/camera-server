import { useEffect, useRef, useState, type RefObject } from "react";
import { Link } from "react-router";

import type { Route } from "./+types/home";

import { Page } from "../components/page";
import { useMjpeg, type FeedStatus } from "../mjpeg";

import "./home.scss";

export function meta({}: Route.MetaArgs) {
  return [{ title: "Front Door Camera · Camera Server" }];
}

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now.toLocaleTimeString("en-GB");
}

function useFullscreen(ref: RefObject<HTMLElement | null>) {
  const [active, setActive] = useState(false);

  useEffect(() => {
    const sync = () => setActive(document.fullscreenElement === ref.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, [ref]);

  const toggle = () => {
    const request = document.fullscreenElement
      ? document.exitFullscreen()
      : ref.current?.requestFullscreen();
    request?.catch(() => {});
  };

  return { active, toggle, supported: document.fullscreenEnabled };
}

function LiveStatus({ status }: { status: FeedStatus }) {
  return (
    <span className="status">
      <span className={`status-dot${status === "live" ? " live" : ""}`} />
      {status === "live" ? "LIVE" : "OFFLINE"}
    </span>
  );
}

function LiveVideo({
  src,
  status,
}: {
  src: string | null;
  status: FeedStatus;
}) {
  const clock = useClock();
  const videoRef = useRef<HTMLDivElement>(null);
  const fullscreen = useFullscreen(videoRef);

  return (
    <div className="video" ref={videoRef} onDoubleClick={fullscreen.toggle}>
      {src && <img src={src} alt="Live camera stream" className="video-img" />}
      {status !== "live" && (
        <div className="video-placeholder">
          <span className="video-label">
            {status === "loading" ? "CONNECTING…" : "CAMERA OFFLINE"}
          </span>
        </div>
      )}
      <span className="video-clock">{clock}</span>
      {fullscreen.supported && (
        <button
          type="button"
          className="video-fullscreen"
          onClick={fullscreen.toggle}
          aria-label={
            fullscreen.active ? "Exit fullscreen" : "Enter fullscreen"
          }
          title={fullscreen.active ? "Exit fullscreen" : "Fullscreen"}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path
              d={
                fullscreen.active
                  ? "M7 3v4H3M13 3v4h4M17 13h-4v4M3 13h4v4"
                  : "M3 7V3h4M13 3h4v4M17 13v4h-4M7 17H3v-4"
              }
            />
          </svg>
        </button>
      )}
    </div>
  );
}

const DAYS = [
  { label: "Today", count: 8 },
  { label: "Yesterday", count: 14 },
  { label: "Sep 16, 2026", count: 6 },
  { label: "Sep 15, 2026", count: 11 },
];

const CLIPS = [
  { label: "Person detected", time: "14:32:07 · 0:18", color: "#3b82f6" },
  { label: "Vehicle detected", time: "13:58:44 · 0:22", color: "#f59e0b" },
  { label: "Motion detected", time: "12:10:19 · 0:09", color: "#9ca3af" },
  { label: "Animal detected", time: "10:44:02 · 0:14", color: "#22c55e" },
];

function Sidebar() {
  return (
    <aside className="side">
      <div className="panel">
        <h2 className="panel-title">
          Browse Recordings
          <small>
            <Link to="/directory">Open full view →</Link>
          </small>
        </h2>
      </div>
    </aside>
  );
}

export default function Home() {
  const { src, status } = useMjpeg("/live");

  return (
    <Page actions={<LiveStatus status={status} />}>
      <div className="home">
        <LiveVideo src={src} status={status} />
        <Sidebar />
      </div>
    </Page>
  );
}
