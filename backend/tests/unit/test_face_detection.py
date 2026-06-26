"""Unit tests for the pure trajectory-smoothing/interpolation helpers in
``app.services.face_detection``.

``detect_face_trajectory()`` itself (cv2 + mediapipe, needs a real video and
the bundled .tflite model) is intentionally NOT covered here.
"""
import json

from app.services.face_detection import (
    CropKeyframe,
    _interp_at_time,
    _interpolate_keyframes,
    _moving_average,
    trajectory_to_ffmpeg_crop,
    trajectory_to_json,
)


class TestMovingAverage:
    def test_data_shorter_than_window_returned_unchanged(self):
        data = [(0.0, 0.0, 0.0), (1.0, 10.0, 10.0)]
        assert _moving_average(data, window=5) == data

    def test_smooths_middle_point(self):
        data = [
            (0.0, 0.0, 0.0), (1.0, 10.0, 10.0), (2.0, 20.0, 20.0),
            (3.0, 30.0, 30.0), (4.0, 40.0, 40.0), (5.0, 50.0, 50.0),
            (6.0, 60.0, 60.0),
        ]
        result = _moving_average(data, window=3)
        # index 3: chunk = data[2:5] -> avg x/y = (20+30+40)/3 = 30
        assert result[3] == (3.0, 30.0, 30.0)
        # index 0 (edge): chunk = data[0:2] -> avg = (0+10)/2 = 5
        assert result[0] == (0.0, 5.0, 5.0)

    def test_preserves_timestamps(self):
        data = [(float(i), float(i) * 10, float(i) * 5) for i in range(6)]
        result = _moving_average(data, window=3)
        assert [r[0] for r in result] == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]


class TestInterpAtTime:
    DATA = [(0.0, 0.0, 0.0), (1.0, 10.0, 10.0), (2.0, 20.0, 20.0), (3.0, 30.0, 30.0)]

    def test_before_first_point_clamps(self):
        assert _interp_at_time(self.DATA, -5.0) == (0.0, 0.0)

    def test_after_last_point_clamps(self):
        assert _interp_at_time(self.DATA, 100.0) == (30.0, 30.0)

    def test_exact_point_match(self):
        assert _interp_at_time(self.DATA, 1.0) == (10.0, 10.0)

    def test_linear_interpolation_between_points(self):
        x, y = _interp_at_time(self.DATA, 1.5)
        assert x == 15.0
        assert y == 15.0


class TestInterpolateKeyframes:
    def test_empty_input_returns_empty(self):
        assert _interpolate_keyframes([], 100, 200, duration=5.0, fps=30.0) == []

    def test_keyframe_count_and_dimensions(self):
        smoothed = [(0.0, 0.0, 0.0), (2.0, 100.0, 200.0)]
        kfs = _interpolate_keyframes(smoothed, crop_w=300, crop_h=400, duration=2.0, fps=30.0, interval=0.5)
        # t = 0, 0.5, 1.0, 1.5, 2.0 -> 5 keyframes
        assert len(kfs) == 5
        assert all(kf.w == 300.0 and kf.h == 400.0 for kf in kfs)
        assert kfs[0].t == 0.0
        assert kfs[-1].t == 2.0

    def test_midpoint_is_linearly_interpolated(self):
        smoothed = [(0.0, 0.0, 0.0), (2.0, 100.0, 200.0)]
        kfs = _interpolate_keyframes(smoothed, crop_w=10, crop_h=10, duration=2.0, fps=30.0, interval=1.0)
        mid = next(kf for kf in kfs if kf.t == 1.0)
        assert mid.x == 50.0
        assert mid.y == 100.0


class TestTrajectoryToFfmpegCrop:
    def test_empty_keyframes_returns_static_centered_crop(self):
        # 1080x1920 source is already 9:16, so the centered crop is the
        # full frame with no offset.
        expr = trajectory_to_ffmpeg_crop([], src_width=1080, src_height=1920)
        assert expr == "crop=1080:1920:0:0"

    def test_single_keyframe_no_if_chain(self):
        kfs = [CropKeyframe(t=0.0, x=10.0, y=20.0, w=500.0, h=900.0)]
        expr = trajectory_to_ffmpeg_crop(kfs, src_width=1920, src_height=1080)
        assert expr == "crop=500:900:10:20"

    def test_multiple_keyframes_build_if_chain(self):
        kfs = [
            CropKeyframe(t=0.0, x=0.0, y=0.0, w=500.0, h=900.0),
            CropKeyframe(t=1.0, x=50.0, y=10.0, w=500.0, h=900.0),
        ]
        expr = trajectory_to_ffmpeg_crop(kfs, src_width=1920, src_height=1080)
        assert expr.startswith("crop=500:900:")
        assert "if(gt(t,1.0),50,0)" in expr
        assert "if(gt(t,1.0),10,0)" in expr

    def test_downsamples_to_at_most_31_keyframes(self):
        kfs = [CropKeyframe(t=float(i), x=float(i), y=float(i), w=100.0, h=100.0) for i in range(40)]
        expr = trajectory_to_ffmpeg_crop(kfs, src_width=1920, src_height=1080)
        # x_expr and y_expr each get one "if(gt(t," per keyframe after the
        # first of the (downsampled) 31 keyframes -> 30 + 30 = 60 total.
        assert expr.count("if(gt(t,") == 60


class TestTrajectoryToJson:
    def test_empty_list(self):
        assert trajectory_to_json([]) == "[]"

    def test_round_trips_keyframe_fields(self):
        kfs = [CropKeyframe(t=1.5, x=10.0, y=20.0, w=500.0, h=900.0)]
        parsed = json.loads(trajectory_to_json(kfs))
        assert parsed == [{"t": 1.5, "x": 10.0, "y": 20.0, "w": 500.0, "h": 900.0}]
