import { Link } from "react-router";

import type { Route } from "./+types/directory";

import { Page } from "../components/page";
import {
  folderUrl,
  formatDate,
  formatDuration,
  mediaUrl,
  useListing,
  type Entry,
} from "../recordings";

import "./directory.scss";

export function meta({}: Route.MetaArgs) {
  return [{ title: "Recordings · Camera Server" }];
}

function FolderCard({ entry }: { entry: Extract<Entry, { type: "dir" }> }) {
  return (
    <Link to={folderUrl(entry.path)} className="card">
      <div className="card-thumb folder">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        </svg>
      </div>
      <div className="card-details">
        <div className="card-title">{entry.name}</div>
        <div className="card-meta">
          {entry.count} {entry.count === 1 ? "recording" : "recordings"}
        </div>
      </div>
    </Link>
  );
}

function FileCard({ entry }: { entry: Extract<Entry, { type: "file" }> }) {
  return (
    <a
      href={mediaUrl(entry.path)}
      target="_blank"
      rel="noreferrer"
      className="card"
    >
      <div className="card-thumb video">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
          <path d="M10 8l6 4-6 4z" />
        </svg>
      </div>
      <div className="card-details">
        <div className="card-title">Record</div>
        <div className="card-meta">
          {formatDate(entry.startedAt)} · {formatDuration(entry.duration)}
        </div>
      </div>
    </a>
  );
}

function Breadcrumbs({ path }: { path: string }) {
  const parts = path.split("/").filter(Boolean);

  return (
    <nav className="breadcrumbs">
      {parts.length ? (
        <Link to={folderUrl("")}>Recordings</Link>
      ) : (
        <span className="current">Recordings</span>
      )}
      {parts.map((part, i) => (
        <span key={i} className="breadcrumb">
          <span className="separator">/</span>
          {i === parts.length - 1 ? (
            <span className="current">{part}</span>
          ) : (
            <Link to={folderUrl(parts.slice(0, i + 1).join("/"))}>{part}</Link>
          )}
        </span>
      ))}
    </nav>
  );
}

export default function Directory({ params }: Route.ComponentProps) {
  const path = params["*"] ?? "";
  const { entries, error } = useListing(path);

  return (
    <Page
      section="directory"
      actions={
        <Link to="/" className="link">
          ← Back to live
        </Link>
      }
    >
      <div className="directory-list">
        <Breadcrumbs path={path} />
        {error && <div className="empty-state">{error}</div>}
        {!error && entries === null && (
          <div className="empty-state">Loading…</div>
        )}
        {entries?.length === 0 && (
          <div className="empty-state">This folder is empty.</div>
        )}
        {entries && entries.length > 0 && (
          <div className="cards">
            {entries.map((entry) =>
              entry.type === "dir" ? (
                <FolderCard key={entry.path} entry={entry} />
              ) : (
                <FileCard key={entry.path} entry={entry} />
              ),
            )}
          </div>
        )}
      </div>
    </Page>
  );
}
