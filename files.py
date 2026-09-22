import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

VIDEO_SUFFIXES = {".mp4"}
THUMBNAIL_SUFFIXES = {".jpg"}
DAY_FORMAT = "%d-%m-%Y"
FILE_FORMAT = "%d-%m-%Y_%H-%M-%S"


def _parse_utc(name, fmt):
    try:
        return datetime.strptime(name, fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _is_video(path):
    return path.suffix.lower() in VIDEO_SUFFIXES and path.is_file()


def _is_thumbnail(path):
    return path.suffix.lower() in THUMBNAIL_SUFFIXES and path.is_file()


def probe_duration(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return float(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def generate_thumbnail(path):
    thumbnail = path.with_suffix(".jpg")
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-ss",
                "00:00:01",
                "-i",
                str(path),
                "-frames:v",
                "1",
                str(thumbnail),
            ],
            capture_output=True,
            timeout=10,
        )
        return thumbnail if result.returncode == 0 and thumbnail.is_file() else None
    except (OSError, subprocess.SubprocessError):
        return None


class Library:
    def __init__(self, root, conn):
        self.root = Path(root).resolve()
        self.conn = conn

    def resolve(self, relative):
        path = (self.root / relative).resolve()
        if path != self.root:
            if self.root not in path.parents:
                raise HTTPException(404)
            if any(part.startswith(".") for part in path.relative_to(self.root).parts):
                raise HTTPException(404)
        if not path.exists():
            raise HTTPException(404)
        return path

    def relative(self, path):
        return "" if path == self.root else path.relative_to(self.root).as_posix()

    def list(self, relative):
        if relative == "":
            return self._list_days()
        if _parse_utc(relative, DAY_FORMAT) is None:
            raise HTTPException(404)
        return self._list_videos(relative)

    def video(self, relative):
        path = self.resolve(relative)
        if not _is_video(path):
            raise HTTPException(404)
        return path

    def thumbnail(self, relative):
        path = self.resolve(relative)
        if not _is_thumbnail(path):
            raise HTTPException(404)
        return path

    def _list_days(self):
        rows = self.conn.execute(
            "SELECT date, COUNT(*) FROM videos GROUP BY date"
        ).fetchall()
        days = [(day, count) for day, count in rows if _parse_utc(day, DAY_FORMAT)]
        days.sort(key=lambda row: _parse_utc(row[0], DAY_FORMAT), reverse=True)
        return [
            {"name": day, "path": day, "type": "dir", "count": count}
            for day, count in days
        ]

    def _list_videos(self, day):
        rows = self.conn.execute(
            "SELECT name, path, duration, thumbnail FROM videos WHERE date = ?",
            (day,),
        ).fetchall()
        fallback = datetime.min.replace(tzinfo=timezone.utc)
        videos = [
            {
                "name": name,
                "path": path,
                "type": "file",
                "startedAt": (
                    _parse_utc(Path(name).stem, FILE_FORMAT) or fallback
                ).isoformat(),
                "duration": duration,
                "thumbnail": thumbnail,
            }
            for name, path, duration, thumbnail in rows
        ]
        videos.sort(key=lambda v: v["startedAt"], reverse=True)
        return videos


def create_router(library):
    router = APIRouter(prefix="/api")

    @router.get("/files")
    def list_files(path: str = ""):
        return {"entries": library.list(path)}

    @router.get("/media/{path:path}")
    def media(path: str):
        return FileResponse(library.video(path), media_type="video/mp4")

    @router.get("/thumbnail/{path:path}")
    def thumbnail(path: str):
        return FileResponse(library.thumbnail(path), media_type="image/jpeg")

    return router
