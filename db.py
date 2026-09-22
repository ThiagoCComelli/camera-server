import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY,
    track_id   INTEGER NOT NULL,
    label      TEXT NOT NULL,
    start      REAL NOT NULL,
    end        REAL NOT NULL,
    duration   REAL NOT NULL,
    confidence REAL NOT NULL,
    x INTEGER, y INTEGER, w INTEGER, h INTEGER
);
CREATE INDEX IF NOT EXISTS events_start ON events (start);

CREATE TABLE IF NOT EXISTS videos (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    path      TEXT NOT NULL UNIQUE,
    date      TEXT NOT NULL,
    duration  REAL,
    thumbnail TEXT
);
CREATE INDEX IF NOT EXISTS videos_date ON videos (date);
"""


def connect(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.executescript(SCHEMA)
    return conn


def events_sink(conn):
    def sink(event):
        x, y, w, h = event["box"]
        conn.execute(
            "INSERT INTO events (track_id, label, start, end, duration, confidence, x, y, w, h)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event["track_id"],
                event["label"],
                event["start"],
                event["end"],
                event["duration"],
                event["confidence"],
                x,
                y,
                w,
                h,
            ),
        )
        conn.commit()

    return sink


def videos_remove_sink(conn):
    def sink(paths):
        conn.executemany(
            "DELETE FROM videos WHERE path = ?",
            [(str(path),) for path in paths],
        )
        conn.commit()

    return sink


def videos_sink(conn):
    def sink(video):
        conn.execute(
            "INSERT INTO videos (name, path, date, duration, thumbnail)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(path) DO UPDATE SET"
            " duration = excluded.duration, thumbnail = excluded.thumbnail",
            (
                video["name"],
                video["path"],
                video["date"],
                video.get("duration"),
                video.get("thumbnail"),
            ),
        )
        conn.commit()

    return sink
