from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_script_module(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check_demo_video = load_script_module(
    "askdu_test_check_demo_video",
    "scripts/check_demo_video.py",
)
mux_demo_narration = load_script_module(
    "askdu_test_mux_demo_narration",
    "scripts/mux_demo_narration.py",
)


def video_probe(*, audio: dict[str, Any] | None = None) -> dict[str, Any]:
    streams: list[dict[str, Any]] = [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1600,
            "height": 900,
            "pix_fmt": "yuv420p",
            "r_frame_rate": "25/1",
        }
    ]
    if audio is not None:
        streams.append(audio)
    return {
        "streams": streams,
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": "27.32",
            "size": "2000000",
        },
    }


def narration_stream(**updates: Any) -> dict[str, Any]:
    stream: dict[str, Any] = {
        "codec_type": "audio",
        "codec_name": "aac",
        "sample_rate": "48000",
        "channels": 1,
        "duration": "27.307",
    }
    stream.update(updates)
    return stream


def test_submission_gate_checks_audio_format_and_timeline() -> None:
    summary = check_demo_video.validate_probe(
        video_probe(audio=narration_stream()),
        mode="submission",
        max_seconds=300,
        max_bytes=50 * 1024 * 1024,
    )

    assert summary["audio_codec"] == "aac"
    assert summary["audio_sample_rate_hz"] == 48_000
    assert summary["audio_duration_seconds"] == 27.307

    with pytest.raises(ValueError, match="sample rate"):
        check_demo_video.validate_probe(
            video_probe(audio=narration_stream(sample_rate="22050")),
            mode="submission",
            max_seconds=300,
            max_bytes=50 * 1024 * 1024,
        )

    with pytest.raises(ValueError, match="cover the walkthrough"):
        check_demo_video.validate_probe(
            video_probe(audio=narration_stream(duration="20")),
            mode="submission",
            max_seconds=300,
            max_bytes=50 * 1024 * 1024,
        )


def test_mux_input_gate_rejects_incomplete_or_overrunning_narration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = tmp_path / "video.mp4"
    narration = tmp_path / "narration.wav"
    output = tmp_path / "output.mp4"
    video.touch()
    narration.touch()

    def fake_probe(path: Path) -> dict[str, Any]:
        if path == video:
            return {
                "format": {"duration": "27.32"},
                "streams": [{"codec_type": "video"}],
            }
        return {
            "format": {"duration": "5"},
            "streams": [{"codec_type": "audio"}],
        }

    monkeypatch.setattr(mux_demo_narration, "probe_media", fake_probe)
    with pytest.raises(ValueError, match="too short"):
        mux_demo_narration.validate_inputs(
            video,
            narration,
            output,
            minimum_fraction=0.6,
            max_overrun_seconds=0.5,
        )

    def overrun_probe(path: Path) -> dict[str, Any]:
        if path == video:
            return {
                "format": {"duration": "27.32"},
                "streams": [{"codec_type": "video"}],
            }
        return {
            "format": {"duration": "30"},
            "streams": [{"codec_type": "audio"}],
        }

    monkeypatch.setattr(mux_demo_narration, "probe_media", overrun_probe)
    with pytest.raises(ValueError, match="overruns"):
        mux_demo_narration.validate_inputs(
            video,
            narration,
            output,
            minimum_fraction=0.6,
            max_overrun_seconds=0.5,
        )


def test_mux_input_gate_accepts_timeline_spanning_narration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = tmp_path / "video.mp4"
    narration = tmp_path / "narration.wav"
    output = tmp_path / "output.mp4"
    video.touch()
    narration.touch()

    def fake_probe(path: Path) -> dict[str, Any]:
        if path == video:
            return {
                "format": {"duration": "27.32"},
                "streams": [{"codec_type": "video"}],
            }
        return {
            "format": {"duration": "27"},
            "streams": [{"codec_type": "audio"}],
        }

    monkeypatch.setattr(mux_demo_narration, "probe_media", fake_probe)
    durations = mux_demo_narration.validate_inputs(
        video,
        narration,
        output,
        minimum_fraction=0.6,
        max_overrun_seconds=0.5,
    )

    assert durations == (27.32, 27.0)
