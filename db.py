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
