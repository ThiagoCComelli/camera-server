import argparse
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

import db
from capture import Capture
from files import Library
from live import LatestFrame
from recorder import ChunkedRecorder
from server import create_app

CHUNK_MINUTES = 5
MIN_FREE_GB = 5
LIVE_HOST = "0.0.0.0"
LIVE_PORT = 8000


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        action="store",
        help="full path to the output directory",
        required=True,
    )
    parser.add_argument(
        "--input",
        action="store",
        help="video input device (default: 7)",
        default=7,
    )
    parser.add_argument(
        "--output-fps",
        action="store",
        type=int,
        help="frames per second to record (default: 10)",
        default=10,
    )
    parser.add_argument(
        "--web-dir",
        action="store",
        help="built React app to serve at / (default: client/build/client next to main.py)",
        default=Path(__file__).parent / "client" / "build" / "client",
        type=Path,
    )
    parser.add_argument(
        "--access-token",
        action="store",
        help="key required for requests from outside the local network "
        "(default: $CAMERA_ACCESS_TOKEN; unset means remote access is refused)",
        default=os.environ.get("CAMERA_ACCESS_TOKEN"),
    )
    return parser.parse_args()


def save_to_all(*sinks):
    def save(event):
        for sink in sinks:
            try:
                sink(event)
            except Exception as exc:
                print(f"Saving event failed ({sink.__qualname__}): {exc}")

    return save


class Server(uvicorn.Server):
    def __init__(self, config, on_shutdown):
        super().__init__(config)
        self._on_shutdown = on_shutdown

    def handle_exit(self, sig, frame):
        self._on_shutdown()
        super().handle_exit(sig, frame)


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = db.connect(output_dir / "events.db")

    web_dir = args.web_dir if (args.web_dir / "index.html").is_file() else None
    if web_dir is None:
        print(f"No React build at {args.web_dir}, serving /live only")

    def request_shutdown():
        latest.close()
        server.should_exit = True

    capture = Capture(args.input, on_exit=request_shutdown)
    recorder = ChunkedRecorder(
        output_dir,
        capture.width,
        capture.height,
        args.output_fps,
        conn,
        CHUNK_MINUTES,
        MIN_FREE_GB,
    )
    latest = LatestFrame()
    capture.add_sink(recorder.write, fps=args.output_fps)
    capture.add_sink(latest.publish)

    @asynccontextmanager
    async def lifespan(_app):
        capture.start()
        yield
        await asyncio.to_thread(capture.stop)
        recorder.close()
        conn.close()

    server = Server(
        uvicorn.Config(
            create_app(
                latest,
                Library(output_dir, conn),
                lifespan,
                web_dir,
                args.access_token,
            ),
            host=LIVE_HOST,
            port=LIVE_PORT,
            timeout_graceful_shutdown=2,
        ),
        on_shutdown=latest.close,
    )
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        recorder.close()
        conn.close()


if __name__ == "__main__":
    main()
