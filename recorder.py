import os
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import db
from files import generate_thumbnail, probe_duration


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
        try:
            self.proc.stdin.close()
        except OSError:  # ffmpeg already died; nothing left to flush
            pass
        self.proc.wait()


class ChunkedRecorder:
    """Encodes frames into fixed-length chunks on its own thread.

    write() is called from the capture thread and never blocks: if the encoder
    falls behind, frames are dropped here instead of stalling the live preview.
    Finished chunks are finalized (moov atom, thumbnail, duration) in the
    background so the next chunk starts recording right away.
    """

    QUEUE_FRAMES = 5  # raw frames are several MB each; keep the backlog short

    def __init__(
        self,
        output_dir,
        width,
        height,
        fps,
        conn,
        chunk_minutes=5,
        min_free_gb=5,
    ):
        self.output_dir = Path(output_dir)
        self.width = width
        self.height = height
        self.fps = fps
        self.chunk_seconds = chunk_minutes * 60
        self.min_free_gb = min_free_gb
        self._save_video = db.videos_sink(conn)
        self._remove_videos = db.videos_remove_sink(conn)
        self._writer = None
        self._chunk_id = None
        self._path = None
        self._finalizers = []
        self._closed = False
        self._queue = queue.Queue(maxsize=self.QUEUE_FRAMES)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._run, name="recorder")
        self._thread.start()

    def write(self, frame):
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            pass

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join()
        for finalizer in self._finalizers:
            finalizer.join()

    def _run(self):
        while (frame := self._queue.get()) is not None:
            chunk_id = int(time.time() // self.chunk_seconds)
            if self._writer is None or chunk_id != self._chunk_id:
                self._finish_chunk()
                if self._free_gb() < self.min_free_gb:
                    self._erase_oldest_day()
                self._writer, self._path = self._create_writer()
                self._chunk_id = chunk_id
            try:
                self._writer.write(frame)
            except OSError as exc:
                print(f"Recording failed, starting a new chunk: {exc}")
                self._finish_chunk()
        self._finish_chunk()

    def _finish_chunk(self):
        if self._writer is None:
            return
        writer, path = self._writer, self._path
        self._writer = self._path = None

        def finalize():
            writer.release()
            self._on_video_saved(path)

        self._finalizers = [t for t in self._finalizers if t.is_alive()]
        finalizer = threading.Thread(target=finalize, name="recorder-finalize")
        finalizer.start()
        self._finalizers.append(finalizer)

    def _create_writer(self):
        now = datetime.now()  # local time, so names match the day the viewer lives in
        day_dir = self.output_dir / now.strftime("%d-%m-%Y")
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{now.strftime('%d-%m-%Y')}_{now.strftime('%H-%M-%S')}.mp4"
        return H264Writer(path, self.width, self.height, self.fps), path

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
        removed = list(days[0].iterdir())
        for file in removed:
            file.unlink()
        days[0].rmdir()
        self._on_videos_removed(removed)

    def _on_video_saved(self, path):
        try:
            thumbnail = generate_thumbnail(path)
            self._save_video(
                {
                    "name": path.name,
                    "path": str(path.relative_to(self.output_dir)),
                    "date": path.parent.name,
                    "duration": probe_duration(path),
                    "thumbnail": str(thumbnail.relative_to(self.output_dir))
                    if thumbnail
                    else None,
                }
            )
        except Exception as exc:
            print(f"Saving video record failed: {exc}")

    def _on_videos_removed(self, paths):
        try:
            self._remove_videos(
                [str(path.relative_to(self.output_dir)) for path in paths]
            )
        except Exception as exc:
            print(f"Removing video records failed: {exc}")
