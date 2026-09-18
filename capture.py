import threading
import time

import cv2


class RateLimiter:
    """ready() is true at most `rate` times per second, without drifting slow."""

    def __init__(self, rate):
        self.interval = 1 / rate
        self._next = time.monotonic()

    def ready(self):
        now = time.monotonic()
        if now < self._next:
            return False
        self._next += self.interval
        if self._next < now:  # fell behind: don't burst to catch up
            self._next = now + self.interval
        return True


class Capture:
    """Reads the camera on a thread and hands every frame to the registered sinks."""

    def __init__(self, source, on_exit=None):
        self._cap = cv2.VideoCapture(source)
        if not self._cap.isOpened():
            raise RuntimeError(f"could not open video input {source!r}")
        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._on_exit = on_exit
        self._sinks = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="capture")

    def add_sink(self, sink, fps=None):
        if fps is not None:
            limiter = RateLimiter(fps)
            inner = sink

            def sink(frame):
                if limiter.ready():
                    inner(frame)

        self._sinks.append(sink)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()

    def _run(self):
        try:
            while not self._stop.is_set():
                ret, frame = self._cap.read()
                if not ret:
                    break
                for sink in self._sinks:
                    sink(frame)
        finally:
            self._cap.release()
            if self._on_exit is not None:
                self._on_exit()
