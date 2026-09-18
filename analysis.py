import json
import math
import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import cv2
import numpy as np

DEFAULT_MODEL = Path(__file__).parent / "models" / "yolov8n.onnx"

SECURITY_RELEVANT = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    15: "cat",
    16: "dog",
}
RELEVANT_IDS = np.array(list(SECURITY_RELEVANT))


@dataclass
class Detection:
    label: str
    confidence: float
    box: tuple[int, int, int, int]  # x, y, w, h in source-frame pixels


class YoloDetector:
    """YOLOv8/YOLO11 ONNX model (e.g. yolov8n) running on OpenCV's dnn module."""

    def __init__(self, model_path, conf=0.4, iou=0.5, size=640, labels=None):
        self.net = cv2.dnn.readNetFromONNX(str(model_path))
        self.conf = conf
        self.iou = iou
        self.size = size
        self.labels = set(labels) if labels else None

    def detect(self, frame):
        height, width = frame.shape[:2]
        # letterbox like the model was trained: keep the aspect ratio, pad the rest
        scale = self.size / max(width, height)
        new_w, new_h = round(width * scale), round(height * scale)
        pad_x, pad_y = (self.size - new_w) // 2, (self.size - new_h) // 2
        canvas = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
        canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = cv2.resize(
            frame, (new_w, new_h)
        )

        blob = cv2.dnn.blobFromImage(
            canvas, 1 / 255, (self.size, self.size), swapRB=True
        )
        self.net.setInput(blob)
        return self._postprocess(
            self.net.forward(), (width, height), scale, (pad_x, pad_y)
        )

    def _postprocess(self, out, frame_size, scale, pad):
        width, height = frame_size
        preds = out[0].T  # (anchors, 4 box values + one score per class)
        scores = preds[:, 4 + RELEVANT_IDS]  # ignore every class we don't care about
        class_ids = RELEVANT_IDS[scores.argmax(axis=1)]
        confs = scores.max(axis=1)

        keep = confs >= self.conf
        preds, class_ids, confs = preds[keep], class_ids[keep], confs[keep]
        if not len(confs):
            return []

        x1 = np.clip((preds[:, 0] - preds[:, 2] / 2 - pad[0]) / scale, 0, width)
        y1 = np.clip((preds[:, 1] - preds[:, 3] / 2 - pad[1]) / scale, 0, height)
        x2 = np.clip((preds[:, 0] + preds[:, 2] / 2 - pad[0]) / scale, 0, width)
        y2 = np.clip((preds[:, 1] + preds[:, 3] / 2 - pad[1]) / scale, 0, height)
        boxes = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1).astype(int)

        # per-class NMS, so a person on a bike doesn't suppress the bike
        detections = []
        for i in np.array(
            cv2.dnn.NMSBoxesBatched(
                boxes.tolist(), confs.tolist(), class_ids.tolist(), self.conf, self.iou
            )
        ).flatten():
            label = SECURITY_RELEVANT[class_ids[i]]
            if self.labels and label not in self.labels:
                continue
            x, y, w, h = (int(v) for v in boxes[i])
            detections.append(Detection(label, round(float(confs[i]), 3), (x, y, w, h)))
        return detections


@dataclass
class Track:
    id: int
    label: str
    box: tuple[int, int, int, int]
    confidence: float
    last_seen: float
    anchor: tuple[int, int, int, int]  # box where it last moved
    velocity: tuple[float, float] = (0.0, 0.0)  # center pixels per second


class ObjectTracker:
    """Follows objects across frames and reports the ones that are moving.

    Detections are matched one-to-one to the same-label track whose predicted
    position (last position plus its velocity) is nearest, so every object keeps
    an id, even when two cross paths. A track is compared to its anchor, the place where it
    was last seen moving, and not to the previous frame: slow movement adds up
    until it crosses the threshold, while detector jitter around a resting
    object never does. Thresholds are relative to the box size, so they hold for
    any resolution and any analysis rate.
    """

    def __init__(
        self,
        min_motion=0.05,
        min_area_change=0.15,
        min_pixels=6,
        max_match=1.5,
        max_age=3.0,
    ):
        self.min_motion = min_motion  # box edge shift from the anchor, in box sizes
        self.min_area_change = min_area_change  # box area change from the anchor
        self.min_pixels = (
            min_pixels  # floor for the shift, so tiny far-away boxes don't jitter
        )
        self.max_match = max_match  # farther than this many box sizes = another object
        self.max_age = max_age  # seconds a missed track waits to be found again
        self._tracks = []
        self._next_id = 1

    @property
    def tracks(self):
        return list(self._tracks)

    def update(self, timestamp, detections):
        """Returns the tracks that moved in this frame."""
        self._tracks = [
            t for t in self._tracks if timestamp - t.last_seen <= self.max_age
        ]

        candidates = sorted(
            (self._distance(t, d, timestamp), ti, di)
            for ti, t in enumerate(self._tracks)
            for di, d in enumerate(detections)
            if t.label == d.label
        )
        used_tracks, used_detections, moving = set(), set(), []
        for distance, ti, di in candidates:
            if distance > self.max_match:
                break
            if ti in used_tracks or di in used_detections:
                continue
            used_tracks.add(ti)
            used_detections.add(di)
            if self._observe(self._tracks[ti], detections[di], timestamp):
                moving.append(self._tracks[ti])

        for di, d in enumerate(detections):
            if di not in used_detections:
                self._tracks.append(
                    Track(self._next_id, d.label, d.box, d.confidence, timestamp, d.box)
                )
                self._next_id += 1
        return moving

    @staticmethod
    def _distance(track, detection, timestamp):
        cx, cy, _ = _pose(track.box)
        dt = min(timestamp - track.last_seen, 1.0)
        cx, cy = cx + track.velocity[0] * dt, cy + track.velocity[1] * dt
        dx, dy, _ = _pose(detection.box)
        size = max(*track.box[2:], *detection.box[2:], 1)
        return math.hypot(cx - dx, cy - dy) / size

    def _observe(self, track, detection, timestamp):
        cx, cy, area = _pose(detection.box)
        size = max(detection.box[2:], default=1)
        # compare the edges, not the center: an object cut by the frame border
        # (or one that leans and waves) moves its box edges more than its center
        shift = max(
            abs(a - b) for a, b in zip(_edges(detection.box), _edges(track.anchor))
        )
        anchor_area = _pose(track.anchor)[2]
        area_change = abs(area - anchor_area) / max(area, anchor_area, 1)

        dt = max(timestamp - track.last_seen, 1e-3)
        px, py, _ = _pose(track.box)
        vx, vy = (cx - px) / dt, (cy - py) / dt
        track.velocity = (
            (track.velocity[0] + vx) / 2,
            (track.velocity[1] + vy) / 2,
        )
        track.box = detection.box
        track.confidence = detection.confidence
        track.last_seen = timestamp
        if shift > max(self.min_motion * size, self.min_pixels) or (
            area_change > self.min_area_change
        ):
            track.anchor = detection.box
            return True
        return False


def _edges(box):
    x, y, w, h = box
    return x, y, x + w, y + h


def _pose(box):
    x, y, w, h = box
    return x + w / 2, y + h / 2, w * h


class LiveAnalyzer:
    """Runs the detector on a worker thread so recording never waits on inference.

    If the detector is still busy, new frames are dropped instead of queued.
    """

    def __init__(self, detector, on_result):
        self.detector = detector
        self.on_result = on_result
        self._queue = queue.Queue(maxsize=1)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, frame, timestamp):
        try:
            self._queue.put_nowait((frame, timestamp))
        except queue.Full:
            pass

    def stop(self):
        self._queue.put(None)
        self._thread.join()

    def _run(self):
        while (item := self._queue.get()) is not None:
            frame, timestamp = item
            try:
                self.on_result(timestamp, self.detector.detect(frame))
            except Exception as exc:
                print(f"Analysis failed: {exc}")


class EventGrouper:
    def __init__(self, on_event, gap_seconds=5.0, min_moves=2, on_start=None):
        self.on_event = on_event
        self.on_start = on_start
        self.gap_seconds = gap_seconds
        self.min_moves = min_moves
        self._open = {}
        self._pending = {}

    @property
    def open_ids(self):
        """Ids of the tracks that currently have an open event."""
        return set(self._open)

    def update(self, timestamp, moving_tracks):
        """Call on every analysed frame, even with no moving tracks, so events can close."""
        for track in moving_tracks:
            event = self._open.get(track.id)
            if event is None:
                event = self._confirm(track, timestamp)
            if event is None:
                continue
            event["end"] = timestamp
            if track.confidence > event["confidence"]:
                event["confidence"] = track.confidence
                event["box"] = track.box

        for track_id, event in list(self._open.items()):
            if timestamp - event["end"] > self.gap_seconds:
                self._close(track_id)
        self._pending = {
            i: p
            for i, p in self._pending.items()
            if timestamp - p["end"] <= self.gap_seconds
        }

    def flush(self):
        for track_id in list(self._open):
            self._close(track_id)
        self._pending.clear()

    def _confirm(self, track, timestamp):
        """Counts a movement; returns the event once it is confirmed, else None."""
        pending = self._pending.get(track.id)
        if pending is None:
            pending = self._pending[track.id] = {
                "track_id": track.id,
                "label": track.label,
                "start": timestamp,
                "end": timestamp,
                "confidence": track.confidence,
                "box": track.box,
                "moves": 0,
            }
        pending["moves"] += 1
        pending["end"] = timestamp
        if pending["confidence"] < track.confidence:
            pending["confidence"], pending["box"] = track.confidence, track.box
        if pending["moves"] < self.min_moves:
            return None

        del self._pending[track.id]
        del pending["moves"]
        self._open[track.id] = pending
        if self.on_start:
            self.on_start(pending)
        return pending

    def _close(self, track_id):
        event = self._open.pop(track_id)
        event["duration"] = round(event["end"] - event["start"], 2)
        self.on_event(event)


class Preview:
    """Draws the last analysis result over live frames.

    The worker thread calls update() after every analysed frame and the display
    loop calls draw() on every captured frame; each update replaces the whole
    snapshot at once, so no lock is needed.
    """

    COLORS = {
        "event": (0, 200, 0),
        "moving": (0, 165, 255),
        "static": (140, 140, 140),
    }

    def __init__(self):
        self._objects = []

    def update(self, timestamp, tracks, moving, open_ids):
        moving_ids = {t.id for t in moving}
        self._objects = [
            (
                t,
                "event"
                if t.id in open_ids
                else "moving"
                if t.id in moving_ids
                else "static",
            )
            for t in tracks
            if t.last_seen == timestamp
        ]

    def draw(self, frame):
        """Returns an annotated copy; the original frame is used for recording."""
        frame = frame.copy()
        for track, state in self._objects:
            x, y, w, h = track.box
            color = self.COLORS[state]
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            text = f"{track.label} #{track.id} {track.confidence:.2f} {state}"
            cv2.putText(
                frame,
                text,
                (x + 4, max(y + 18, 18)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
            )
        return frame


class MotionMonitor:
    """The whole live pipeline: detect, track, group into events, optionally preview.

    submit() hands over a frame without blocking; everything else runs on the
    analyzer thread. Call stop() at the end to finish pending work and save any
    event still open.
    """

    def __init__(
        self, detector, on_event, gap_seconds=5.0, on_start=None, preview=None
    ):
        self.tracker = ObjectTracker()
        self.grouper = EventGrouper(on_event, gap_seconds, on_start=on_start)
        self.preview = preview
        self._analyzer = LiveAnalyzer(detector, self._on_result)

    def submit(self, frame, timestamp):
        self._analyzer.submit(frame, timestamp)

    def stop(self):
        self._analyzer.stop()
        self.grouper.flush()

    def _on_result(self, timestamp, detections):
        moving = self.tracker.update(timestamp, detections)
        self.grouper.update(timestamp, moving)
        if self.preview is not None:
            self.preview.update(
                timestamp, self.tracker.tracks, moving, self.grouper.open_ids
            )


def daily_events_sink(output_dir):
    """Appends events to <output_dir>/<dd-mm-YYYY>/events.jsonl (day the event started)."""

    def sink(event):
        start = datetime.fromtimestamp(event["start"], tz=ZoneInfo("UTC"))
        end = datetime.fromtimestamp(event["end"], tz=ZoneInfo("UTC"))
        day_dir = Path(output_dir) / start.strftime("%d-%m-%Y")
        day_dir.mkdir(parents=True, exist_ok=True)
        record = {**event, "start": start.isoformat(), "end": end.isoformat()}
        with open(day_dir / "events.jsonl", "a") as f:
            f.write(json.dumps(record) + "\n")

    return sink
