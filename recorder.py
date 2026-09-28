import os
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2

import db

HARDWARE_ENCODER = "h264_v4l2m2m"  # the Raspberry Pi 4's H.264 block
SOFTWARE_ENCODER = "libx264"
THUMBNAIL_WIDTH = 320


def _ffmpeg_command(encoder, width, height, fps):
    """ffmpeg reading raw BGR frames from stdin, up to (not including) the output."""
    if encoder == HARDWARE_ENCODER:
        # the hardware encoder targets a bitrate; ~0.07 bits per pixel is plenty
        # for a mostly static camera view (about 1.5 Mbit/s at 1080p, 10 fps)
        bitrate = max(500_000, int(width * height * fps * 0.07))
        codec = ["-c:v", HARDWARE_ENCODER, "-b:v", str(bitrate)]
    else:
        codec = ["-c:v", SOFTWARE_ENCODER, "-preset", "ultrafast"]
    return [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        # stamp frames with when they arrive, so dropped frames leave a gap in
        # time instead of making the video shorter and play fast
        "-use_wallclock_as_timestamps",
        "1",
        "-framerate",  # only sets the timestamp precision (1 ms); the default
        "1000",  # 1/25 s merges frames above 25 fps
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-i",
        "-",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-pix_fmt",
        "yuv420p",
        *codec,
        "-g",
        str(fps * 2),
        "-fps_mode",
        "vfr",
    ]


def pick_encoder(width, height, fps):
    """The hardware encoder if it really works here, else x264.

    ffmpeg lists h264_v4l2m2m on any Linux build, even without the hardware, so
    it is tried on one blank frame rather than looked up.
    """
    command = _ffmpeg_command(HARDWARE_ENCODER, width, height, fps)
    try:
        result = subprocess.run(
            [*command, "-frames:v", "1", "-f", "null", "-"],
            input=bytes(width * height * 3),
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return SOFTWARE_ENCODER
    return HARDWARE_ENCODER if result.returncode == 0 else SOFTWARE_ENCODER


class H264Writer:
    def __init__(self, path, width, height, fps, encoder):
        self.proc = subprocess.Popen(
            [
                *_ffmpeg_command(encoder, width, height, fps),
                # fragmented MP4: written as it goes, so closing it needs no
                # rewrite of the whole file, and a crash leaves it playable
                "-movflags",
                "+frag_keyframe+empty_moov+delay_moov+default_base_moof",
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
    Closing a chunk is cheap (fragmented MP4, thumbnail taken from the first
    frame, duration from the clock), so the next one starts right away.
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
        self.encoder = pick_encoder(width, height, fps)
        self._save_video = db.videos_sink(conn)
        self._remove_videos = db.videos_remove_sink(conn)
        self._writer = None
        self._chunk_id = None
        self._path = None
        self._thumbnail = None
        self._started = self._last_frame = 0.0
        self._closed = False
        self._queue = queue.Queue(maxsize=self.QUEUE_FRAMES)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Recording with {self.encoder}")
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

    def _run(self):
        while (frame := self._queue.get()) is not None:
            chunk_id = int(time.time() // self.chunk_seconds)
            if self._writer is None or chunk_id != self._chunk_id:
                self._finish_chunk()
                if self._free_gb() < self.min_free_gb:
                    self._erase_oldest_day()
                self._start_chunk(frame)
                self._chunk_id = chunk_id
            try:
                self._writer.write(frame)
                self._last_frame = time.monotonic()
            except OSError as exc:
                print(f"Recording failed, starting a new chunk: {exc}")
                self._finish_chunk()
        self._finish_chunk()

    def _start_chunk(self, frame):
        now = datetime.now()  # local time, so names match the day the viewer lives in
        day_dir = self.output_dir / now.strftime("%d-%m-%Y")
        day_dir.mkdir(parents=True, exist_ok=True)
        self._path = day_dir / f"{now.strftime('%d-%m-%Y')}_{now.strftime('%H-%M-%S')}.mp4"
        self._writer = H264Writer(
            self._path, self.width, self.height, self.fps, self.encoder
        )
        self._thumbnail = self._write_thumbnail(frame, self._path.with_suffix(".jpg"))
        self._started = self._last_frame = time.monotonic()

    def _finish_chunk(self):
        if self._writer is None:
            return
        self._writer.release()
        self._on_video_saved(
            self._path,
            self._last_frame - self._started + 1 / self.fps,
            self._thumbnail,
        )
        self._writer = self._path = self._thumbnail = None

    def _write_thumbnail(self, frame, path):
        height, width = frame.shape[:2]
        scale = THUMBNAIL_WIDTH / width
        small = cv2.resize(
            frame,
            (THUMBNAIL_WIDTH, round(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
        return path if cv2.imwrite(str(path), small) else None

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

    def _on_video_saved(self, path, duration, thumbnail):
        try:
            self._save_video(
                {
                    "name": path.name,
                    "path": str(path.relative_to(self.output_dir)),
                    "date": path.parent.name,
                    "duration": round(duration, 2),
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
