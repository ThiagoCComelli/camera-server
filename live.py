import asyncio
import threading

import cv2
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

FRAME_WAIT_SECONDS = 5


class LatestFrame:
    """Holds the newest camera frame and JPEG-encodes it only when a viewer asks.

    publish() runs on the capture thread, so it just swaps a reference: nothing is
    encoded while nobody watches, and every viewer shares one encode per frame.
    """

    def __init__(self, quality=100, max_width=None):
        self._quality = quality
        self._max_width = max_width
        self._cond = threading.Condition()
        self._frame = None
        self._seq = 0
        self._closed = False
        self._encode_lock = threading.Lock()
        self._jpeg = None
        self._jpeg_seq = -1

    @property
    def closed(self):
        return self._closed

    def publish(self, frame):
        with self._cond:
            self._frame = frame
            self._seq += 1
            self._cond.notify_all()

    def wait_next(self, last_seq, timeout=FRAME_WAIT_SECONDS):
        """Returns (seq, jpeg) of the newest frame once it differs from last_seq."""
        with self._cond:
            self._cond.wait_for(lambda: self._closed or self._seq != last_seq, timeout)
            seq, frame = self._seq, self._frame
        if frame is None:
            return seq, None
        return self._encode(seq, frame)

    def close(self):
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def _encode(self, seq, frame):
        with self._encode_lock:
            if self._jpeg_seq < seq:
                height, width = frame.shape[:2]
                if self._max_width and width > self._max_width:
                    size = (self._max_width, round(height * self._max_width / width))
                    frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
                ok, buf = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._quality]
                )
                if not ok:
                    return seq, None
                self._jpeg, self._jpeg_seq = buf.tobytes(), seq
            return self._jpeg_seq, self._jpeg


def create_router(latest):
    router = APIRouter()

    @router.get("/live")
    async def live():
        """Continuous MJPEG, for direct LAN viewers (VLC, a bare <img>). Behind a
        proxy it queues frames and lags; the app polls /live/frame instead."""

        async def stream():
            seq = 0
            while not latest.closed:
                seq, jpeg = await asyncio.to_thread(latest.wait_next, seq)
                if jpeg is None or latest.closed:
                    continue
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n"
                    b"Content-Length: "
                    + str(len(jpeg)).encode()
                    + b"\r\n\r\n"
                    + jpeg
                    + b"\r\n"
                )

        return StreamingResponse(
            stream(), media_type="multipart/x-mixed-replace; boundary=frame"
        )

    @router.get("/live/frame")
    async def frame(after: int = 0):
        """The newest frame, waiting for one newer than `after` if needed.

        The client asks for the next frame only after the previous one arrived, so
        at most one frame is ever in flight: a slow link lowers the frame rate
        instead of building up delay in proxy buffers.
        """
        seq, jpeg = await asyncio.to_thread(latest.wait_next, after)
        if jpeg is None or latest.closed:
            raise HTTPException(503, "No camera frame available")
        return Response(
            jpeg,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store", "X-Frame-Seq": str(seq)},
        )

    return router
