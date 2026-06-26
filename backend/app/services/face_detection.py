"""Active speaker detection and auto-reframe trajectory generation.

This module analyzes a video file frame-by-frame using MediaPipe's face
detector and produces a **crop trajectory** — a list of (time, x, y, w, h)
tuples that tell ffmpeg where to crop the 16:9 source to produce a smooth
9:16 vertical video that follows the speaker's face.

Pipeline:
  1. Sample frames at ~2 FPS (every 15 frames at 30fps) for speed
  2. Run face detection on each sampled frame
  3. Convert each detection to a target crop rectangle (9:16 aspect)
  4. Smooth the trajectory with a moving-average filter
  5. Interpolate to the video's FPS for frame-accurate cropping
  6. If no faces are found at all, return an empty list and the caller
     falls back to the "centered" layout

The output is consumed by ``vertical_editor_service._build_simple_filter``
which emits ffmpeg ``crop=...`` filter expressions with time-varying
parameters.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Default model path (relative to the backend data dir)
_DEFAULT_MODEL = "data/models/face_detection_short_range.tflite"


@dataclass
class CropKeyframe:
    """One keyframe in the crop trajectory.

    Times are in seconds (relative to the clip start). Coordinates are
    in pixels in the source video's coordinate space. w/h are the crop
    rectangle dimensions.
    """

    t: float    # time in seconds
    x: float    # top-left x of crop rect
    y: float    # top-left y of crop rect
    w: float    # width of crop rect
    h: float    # height of crop rect

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DetectionResult:
    """Summary of the face-detection pass for logging/debugging."""

    total_frames: int
    frames_with_faces: int
    detection_rate: float       # frames_with_faces / total_frames
    trajectory_length: int      # number of keyframes after smoothing
    model_used: str
    fallback: bool              # True if no faces → centered fallback

    def to_dict(self) -> dict:
        return asdict(self)


# ── Core detection ────────────────────────────────────────────────────────

def detect_face_trajectory(
    video_path: str | Path,
    target_width: int = 1080,
    target_height: int = 1920,
    sample_every_n_frames: int = 15,
    smoothing_window: int = 5,
    model_path: str | None = None,
) -> tuple[list[CropKeyframe], DetectionResult]:
    """Analyze a video and return a smooth crop trajectory for 9:16.

    Args:
        video_path: Path to the source video (16:9 or any aspect).
        target_width: Output width (default 1080 for 9:16).
        target_height: Output height (default 1920 for 9:16).
        sample_every_n_frames: Detect faces every N frames (15 = ~2 FPS
            at 30fps). Lower = more precise but slower.
        smoothing_window: Moving-average window size. Higher = smoother
            but laggier. 5 is a good default.
        model_path: Path to the .tflite model. Defaults to the bundled
            short-range model.

    Returns:
        A tuple of (keyframes, summary). If no faces are found, keyframes
        is empty and ``summary.fallback`` is True.
    """
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    import numpy as np

    model_path = model_path or _DEFAULT_MODEL
    if not Path(model_path).exists():
        logger.error("face_model_not_found", path=model_path)
        return [], DetectionResult(
            total_frames=0, frames_with_faces=0, detection_rate=0.0,
            trajectory_length=0, model_used=model_path, fallback=True,
        )

    # Open video
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error("face_video_open_failed", path=str(video_path))
        return [], DetectionResult(
            total_frames=0, frames_with_faces=0, detection_rate=0.0,
            trajectory_length=0, model_used=model_path, fallback=True,
        )

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if total_frames == 0 or src_w == 0 or src_h == 0:
        cap.release()
        logger.warning("face_video_metadata_invalid", path=str(video_path))
        return [], DetectionResult(
            total_frames=0, frames_with_faces=0, detection_rate=0.0,
            trajectory_length=0, model_used=model_path, fallback=True,
        )

    logger.info(
        "face_detection_start",
        path=str(video_path), fps=fps, total_frames=total_frames,
        src_size=f"{src_w}x{src_h}", sample_every=sample_every_n_frames,
    )

    # Init detector
    options = vision.FaceDetectorOptions(
        base_options=python.BaseOptions(model_asset_path=model_path),
    )
    detector = vision.FaceDetector.create_from_options(options)

    # ── 1. Sample frames and detect faces ──────────────────────────────
    raw_detections: list[tuple[float, float, float]] = []
    # Each entry: (time_sec, face_center_x, face_center_y)

    frame_idx = 0
    frames_processed = 0
    frames_with_faces = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % sample_every_n_frames == 0:
            frames_processed += 1
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            result = detector.detect(mp_image)
            if result.detections:
                frames_with_faces += 1
                # Pick the largest face (most prominent speaker)
                best = max(
                    result.detections,
                    key=lambda d: d.bounding_box.width * d.bounding_box.height,
                )
                bb = best.bounding_box
                cx = bb.origin_x + bb.width / 2
                cy = bb.origin_y + bb.height / 2
                t = frame_idx / fps
                raw_detections.append((t, cx, cy))
        frame_idx += 1

    cap.release()
    detector.close()

    detection_rate = frames_with_faces / frames_processed if frames_processed > 0 else 0.0
    logger.info(
        "face_detection_done",
        frames_processed=frames_processed,
        frames_with_faces=frames_with_faces,
        detection_rate=round(detection_rate, 2),
    )

    # ── 2. No faces → fallback ─────────────────────────────────────────
    if not raw_detections:
        logger.info("face_detection_no_faces_fallback", path=str(video_path))
        return [], DetectionResult(
            total_frames=frames_processed,
            frames_with_faces=0,
            detection_rate=0.0,
            trajectory_length=0,
            model_used=model_path,
            fallback=True,
        )

    # ── 3. Compute crop rectangle for each detection ───────────────────
    # The crop rectangle is centered on the face, sized to the target
    # aspect ratio (9:16), clamped to the source dimensions.
    crop_w = min(src_w, int(src_h * target_width / target_height))
    crop_h = min(src_h, int(crop_w * target_height / target_width))
    # If the source is wider than 9:16, we crop width; if taller, crop height
    if crop_w > src_w:
        crop_w = src_w
        crop_h = int(src_w * target_height / target_width)

    raw_crops: list[tuple[float, float, float]] = []
    for t, cx, cy in raw_detections:
        # Center the crop on the face, clamped to source bounds
        x = max(0, min(src_w - crop_w, cx - crop_w / 2))
        y = max(0, min(src_h - crop_h, cy - crop_h / 2))
        raw_crops.append((t, x, y))

    # ── 4. Smooth with moving average ──────────────────────────────────
    smoothed = _moving_average(raw_crops, window=smoothing_window)

    # ── 5. Interpolate to every second (ffmpeg crop uses time expressions) ──
    # We emit one keyframe per second — ffmpeg's crop filter can interpolate
    # between them with `crop='if(gt(t,1),x1,x0)':...` but that's complex.
    # Instead we emit a keyframe every 0.5s and use ffmpeg's `sendcmd` or
    # a per-frame crop expression. For simplicity, we emit at 1s intervals
    # and the filter uses `between(t,a,b)` conditions.
    duration = total_frames / fps
    keyframes = _interpolate_keyframes(smoothed, crop_w, crop_h, duration, fps)

    logger.info(
        "face_trajectory_built",
        keyframes=len(keyframes), duration=round(duration, 1),
        crop_size=f"{crop_w}x{crop_h}",
    )

    return keyframes, DetectionResult(
        total_frames=frames_processed,
        frames_with_faces=frames_with_faces,
        detection_rate=round(detection_rate, 3),
        trajectory_length=len(keyframes),
        model_used=model_path,
        fallback=False,
    )


# ── Helpers ───────────────────────────────────────────────────────────────

def _moving_average(
    data: list[tuple[float, float, float]], window: int = 5,
) -> list[tuple[float, float, float]]:
    """Smooth the (t, x, y) trajectory with a centered moving average."""
    if len(data) <= window:
        return data
    half = window // 2
    result: list[tuple[float, float, float]] = []
    for i in range(len(data)):
        lo = max(0, i - half)
        hi = min(len(data), i + half + 1)
        chunk = data[lo:hi]
        avg_x = sum(d[1] for d in chunk) / len(chunk)
        avg_y = sum(d[2] for d in chunk) / len(chunk)
        result.append((data[i][0], avg_x, avg_y))
    return result


def _interpolate_keyframes(
    smoothed: list[tuple[float, float, float]],
    crop_w: int,
    crop_h: int,
    duration: float,
    fps: float,
    interval: float = 0.5,
) -> list[CropKeyframe]:
    """Interpolate the smoothed trajectory to regular time intervals.

    Emits one CropKeyframe every ``interval`` seconds (default 0.5s).
    Between two raw detections, we linearly interpolate the x/y position.
    """
    if not smoothed:
        return []

    keyframes: list[CropKeyframe] = []
    # Generate timestamps at regular intervals
    n_points = int(duration / interval) + 1
    for i in range(n_points):
        t = i * interval
        if t > duration:
            break
        # Find the two surrounding raw detections
        # (smoothed is sorted by time)
        x, y = _interp_at_time(smoothed, t)
        keyframes.append(CropKeyframe(
            t=round(t, 3),
            x=round(x, 1),
            y=round(y, 1),
            w=float(crop_w),
            h=float(crop_h),
        ))
    return keyframes


def _interp_at_time(
    data: list[tuple[float, float, float]], t: float,
) -> tuple[float, float]:
    """Linear interpolation of (x, y) at time t from sorted data."""
    if t <= data[0][0]:
        return data[0][1], data[0][2]
    if t >= data[-1][0]:
        return data[-1][1], data[-1][2]
    # Binary search for the surrounding pair
    lo, hi = 0, len(data) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if data[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    t0, x0, y0 = data[lo]
    t1, x1, y1 = data[hi]
    if t1 == t0:
        return x0, y0
    alpha = (t - t0) / (t1 - t0)
    return x0 + alpha * (x1 - x0), y0 + alpha * (y1 - y0)


# ── ffmpeg filter expression ──────────────────────────────────────────────

def trajectory_to_ffmpeg_crop(
    keyframes: list[CropKeyframe],
    src_width: int,
    src_height: int,
) -> str:
    """Convert a crop trajectory into an ffmpeg filter expression.

    Uses a compact ``if(lt(t,...),...)`` chain with at most ~30 keyframes
    (downsampled from the full trajectory) to avoid hitting ffmpeg's
    expression nesting limit. The crop size is constant; only x/y change.

    If the trajectory is empty, returns a static centered crop.
    """
    if not keyframes:
        # Fallback: center crop
        crop_w = min(src_width, int(src_height * 1080 / 1920))
        crop_h = int(crop_w * 1920 / 1080)
        x = (src_width - crop_w) / 2
        y = (src_height - crop_h) / 2
        return f"crop={crop_w}:{crop_h}:{x:.0f}:{y:.0f}"

    # Downsample to at most 30 keyframes to keep the expression manageable
    if len(keyframes) > 30:
        step = len(keyframes) / 30
        sampled = [keyframes[int(i * step)] for i in range(30)]
        # Always include the last keyframe
        if sampled[-1] != keyframes[-1]:
            sampled.append(keyframes[-1])
        keyframes = sampled

    kf0 = keyframes[0]
    crop_w = int(kf0.w)
    crop_h = int(kf0.h)

    # Build x expression as a chain of if(gt(t,...)) — left-to-right,
    # each clause overrides the previous when t exceeds the threshold.
    # This is flatter than nested if(between()) and avoids deep nesting.
    x_expr = f"{keyframes[0].x:.0f}"
    for kf in keyframes[1:]:
        x_expr = f"if(gt(t,{kf.t}),{kf.x:.0f},{x_expr})"

    y_expr = f"{keyframes[0].y:.0f}"
    for kf in keyframes[1:]:
        y_expr = f"if(gt(t,{kf.t}),{kf.y:.0f},{y_expr})"

    return f"crop={crop_w}:{crop_h}:{x_expr}:{y_expr}"


def trajectory_to_json(keyframes: list[CropKeyframe]) -> str:
    """Serialize a trajectory to JSON (for debugging / UI preview)."""
    return json.dumps([kf.to_dict() for kf in keyframes])
