"""Maintenance commands for recordings.

    python manage.py --output-dir DIR clear
    python manage.py --output-dir DIR delete-day 28-09-2026

Safe to run while the server records: only videos already in the database are
deleted, and the chunk being recorded is added only once it is finished.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import db
from files import DAY_FORMAT


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="the server's output directory (holds events.db and the day folders)",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="don't ask for confirmation"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("clear", help="delete every video and all database records")
    day = commands.add_parser("delete-day", help="delete every video of one day")
    day.add_argument("day", type=parse_day, help="the day, as DD-MM-YYYY")
    return parser.parse_args()


def parse_day(value):
    try:
        datetime.strptime(value, DAY_FORMAT)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a DD-MM-YYYY day")
    return value


def confirm(question):
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def delete_videos(root, conn, rows):
    """Deletes the records first, so the app never lists a video whose file is
    already gone, then the files, then any day folder left empty."""
    db.videos_remove_sink(conn)([path for path, _ in rows])
    days = set()
    for path, thumbnail in rows:
        for relative in (path, thumbnail):
            if relative:
                (root / relative).unlink(missing_ok=True)
        days.add((root / path).parent)
    for day in days:
        try:
            day.rmdir()
        except OSError:  # still holds other files, e.g. the chunk being recorded
            pass


def size_gb(root, rows):
    files = (root / rel for row in rows for rel in row if rel)
    return sum(f.stat().st_size for f in files if f.is_file()) / 1024**3


def main():
    args = parse_args()
    root = args.output_dir.resolve()
    if not (root / "events.db").is_file():
        sys.exit(f"No events.db in {root}")
    conn = db.connect(root / "events.db")

    if args.command == "clear":
        rows = conn.execute("SELECT path, thumbnail FROM videos").fetchall()
        what = "every video and all events"
    else:
        rows = conn.execute(
            "SELECT path, thumbnail FROM videos WHERE date = ?", (args.day,)
        ).fetchall()
        what = f"the videos of {args.day}"
        if not rows:
            sys.exit(f"No videos recorded on {args.day}")

    question = f"Delete {what} ({len(rows)} videos, {size_gb(root, rows):.2f} GB)?"
    if not args.yes and not confirm(question):
        sys.exit("Nothing deleted")

    delete_videos(root, conn, rows)
    if args.command == "clear":
        conn.execute("DELETE FROM events")
        conn.commit()
    conn.close()
    print(f"Deleted {len(rows)} videos")


if __name__ == "__main__":
    main()
