import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

VIDEO_SUFFIXES = {".mp4"}
DAY_FORMAT = "%d-%m-%Y"
FILE_FORMAT = "%d-%m-%Y_%H-%M-%S"
PROBE_JOBS = 4


def _parse_utc(name, fmt):
    try:
        return datetime.strptime(name, fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _mtime_utc(path):
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)


def _is_video(path):
    return path.suffix.lower() in VIDEO_SUFFIXES and path.is_file()


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


class Library:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self._lock = threading.Lock()
        self._durations = {}
        self._probes = ThreadPoolExecutor(PROBE_JOBS)

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
        folder = self.resolve(relative)
        if not folder.is_dir():
            raise HTTPException(400, "not a folder")

        dirs, files = [], []
        for child in folder.iterdir():
            if child.name.startswith("."):
                continue
            if child.is_dir():
                dirs.append(child)
            elif _is_video(child):
                files.append(child)

        started = {f: _parse_utc(f.stem, FILE_FORMAT) or _mtime_utc(f) for f in files}
        dirs.sort(
            key=lambda d: _parse_utc(d.name, DAY_FORMAT) or _mtime_utc(d), reverse=True
        )
        files.sort(key=started.get, reverse=True)
        durations = self._probes.map(self._duration, files)

        return [
            {
                "name": d.name,
                "path": self.relative(d),
                "type": "dir",
                "count": sum(1 for c in d.iterdir() if _is_video(c)),
            }
            for d in dirs
        ] + [
            {
                "name": f.name,
                "path": self.relative(f),
                "type": "file",
                "startedAt": started[f].isoformat(),
                "duration": duration,
            }
            for f, duration in zip(files, durations)
        ]

    def video(self, relative):
        path = self.resolve(relative)
        if not _is_video(path):
            raise HTTPException(404)
        return path

    def _duration(self, path):
        try:
            stat = path.stat()
        except OSError:
            return None
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if key in self._durations:
                return self._durations[key]
        seconds = probe_duration(path)
        if seconds is not None:
            with self._lock:
                self._durations[key] = seconds
        return seconds


def create_router(library):
    router = APIRouter(prefix="/api")

    @router.get("/files")
    def list_files(path: str = ""):
        return {"entries": library.list(path)}

    @router.get("/media/{path:path}")
    def media(path: str):
        return FileResponse(library.video(path), media_type="video/mp4")

    return router
