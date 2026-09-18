import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class H264Writer:
    def __init__(self, path, width, height, fps):
        self.proc = subprocess.Popen(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "bgr24",
                "-s",
                f"{width}x{height}",
                "-r",
                str(fps),
                "-i",
                "-",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-vf",
                "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(path),
            ],
            stdin=subprocess.PIPE,
            start_new_session=True,
        )

    def write(self, frame):
        self.proc.stdin.write(frame.tobytes())

    def release(self):
        self.proc.stdin.close()
        self.proc.wait()


class ChunkedRecorder:
    def __init__(self, output_dir, width, height, fps, chunk_minutes=5, min_free_gb=5):
        self.output_dir = Path(output_dir)
        self.width = width
        self.height = height
        self.fps = fps
        self.chunk_seconds = chunk_minutes * 60
        self.min_free_gb = min_free_gb
        self._writer = None
        self._chunk_id = None
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, frame):
        chunk_id = int(time.time() // self.chunk_seconds)
        if self._writer is None or chunk_id != self._chunk_id:
            self.close()
            if self._free_gb() < self.min_free_gb:
                self._erase_oldest_day()
            self._writer = self._create_writer()
            self._chunk_id = chunk_id
        self._writer.write(frame)

    def close(self):
        if self._writer is not None:
            writer, self._writer = self._writer, None
            writer.release()

    def _create_writer(self):
        now = datetime.now(tz=ZoneInfo("UTC"))
        day_dir = self.output_dir / now.strftime("%d-%m-%Y")
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{now.strftime('%d-%m-%Y')}_{now.strftime('%H-%M-%S')}.mp4"
        return H264Writer(path, self.width, self.height, self.fps)

    def _free_gb(self):
        stats = os.statvfs(self.output_dir)
        return stats.f_frsize * stats.f_bavail / 1024**3

    def _erase_oldest_day(self):
        days = sorted(
            (d for d in self.output_dir.iterdir() if d.is_dir()),
            key=lambda d: datetime.strptime(d.name, "%d-%m-%Y"),
        )
        if not days:
            return
        for file in days[0].iterdir():
            file.unlink()
        days[0].rmdir()
