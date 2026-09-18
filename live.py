import asyncio
import threading

import cv2
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


class LatestFrame:
    def __init__(self, quality=100):
        self._quality = quality
        self._cond = threading.Condition()
        self._jpeg = None
        self._seq = 0
        self._closed = False

    @property
    def closed(self):
        return self._closed

    def publish(self, frame):
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._quality])
        if not ok:
            return
        with self._cond:
            self._jpeg = buf.tobytes()
            self._seq += 1
            self._cond.notify_all()

    def wait_next(self, last_seq, timeout=5):
        with self._cond:
            self._cond.wait_for(lambda: self._closed or self._seq != last_seq, timeout)
            return self._seq, self._jpeg

    def close(self):
        with self._cond:
            self._closed = True
            self._cond.notify_all()


def create_router(latest):
    router = APIRouter()

    @router.get("/live")
    async def live():
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

    return router
