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
    """Reads the camera on a thread and hands every frame to the registered sinks.

    If the camera can't be opened, or stops delivering frames (unplugged, driver
    hiccup), it is retried every RETRY_SECONDS instead of stopping the server.
    """

    RETRY_SECONDS = 5

    def __init__(self, source):
        self._source = source
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
        failing = False
        while not self._stop.is_set():
            cap = cv2.VideoCapture(self._source)
            try:
                if not cap.isOpened():
                    if not failing:
                        print(
                            f"Could not open video input {self._source!r}, "
                            f"retrying every {self.RETRY_SECONDS} s"
                        )
                    failing = True
                else:
                    failing = False
                    if self._read(cap):
                        print(
                            f"Video input {self._source!r} stopped sending frames, "
                            f"retrying every {self.RETRY_SECONDS} s"
                        )
            finally:
                cap.release()
            self._stop.wait(self.RETRY_SECONDS)

    def _read(self, cap):
        """Feeds frames to the sinks until stopped (False) or the input fails (True)."""
        print(f"Video input {self._source!r} opened")
        while not self._stop.is_set():
            ret, frame = cap.read()
            if not ret:
                return True
            for sink in self._sinks:
                sink(frame)
        return False
