from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE: dict[str, Any] = runpy.run_path(str(PROJECT_ROOT / "scripts/check_demo_video.py"))


def valid_probe() -> dict[str, Any]:
    return {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1600,
                "height": 900,
                "pix_fmt": "yuv420p",
                "r_frame_rate": "25/1",
            }
        ],
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": "31.250",
            "size": "2000000",
        },
    }


def test_draft_gate_accepts_captioned_silent_h264() -> None:
    validate_probe = MODULE["validate_probe"]

    assert validate_probe(
        valid_probe(),
        mode="draft",
        max_seconds=300,
        max_bytes=50 * 1024 * 1024,
    ) == {
        "duration_seconds": 31.25,
        "size_bytes": 2_000_000,
        "container": "mp4",
        "video_codec": "h264",
        "dimensions": "1600x900",
        "pixel_format": "yuv420p",
        "frame_rate": "25/1",
        "audio_streams": 0,
        "mode": "draft",
    }


def test_submission_gate_requires_aac_narration() -> None:
    validate_probe = MODULE["validate_probe"]
    probe = valid_probe()

    with pytest.raises(ValueError, match="exactly one narration"):
        validate_probe(
            probe,
            mode="submission",
            max_seconds=300,
            max_bytes=50 * 1024 * 1024,
        )
    probe["streams"].append(
        {
            "codec_type": "audio",
            "codec_name": "aac",
            "sample_rate": "48000",
            "channels": 1,
            "duration": "31.24",
        }
    )
    assert (
        validate_probe(
            probe,
            mode="submission",
            max_seconds=300,
            max_bytes=50 * 1024 * 1024,
        )["audio_streams"]
        == 1
    )


def test_submission_gate_rejects_silent_level_measurements() -> None:
    validate_audio_levels = MODULE["validate_audio_levels"]
    validate_audio_levels({"mean_volume_db": -28.0, "max_volume_db": -7.0})

    with pytest.raises(ValueError, match="mean level"):
        validate_audio_levels({"mean_volume_db": -91.0, "max_volume_db": -91.0})

    with pytest.raises(ValueError, match="peak level"):
        validate_audio_levels({"mean_volume_db": -45.0, "max_volume_db": -35.0})


def test_gate_rejects_wrong_video_format_or_limit() -> None:
    validate_probe = MODULE["validate_probe"]
    probe = valid_probe()
    probe["streams"][0]["pix_fmt"] = "yuv444p"
    with pytest.raises(ValueError, match="yuv420p"):
        validate_probe(
            probe,
            mode="draft",
            max_seconds=300,
            max_bytes=50 * 1024 * 1024,
        )

    probe = valid_probe()
    probe["format"]["format_name"] = "matroska,webm"
    with pytest.raises(ValueError, match="container must be MP4"):
        validate_probe(
            probe,
            mode="draft",
            max_seconds=300,
            max_bytes=50 * 1024 * 1024,
        )

    probe = valid_probe()
    probe["format"]["size"] = str(51 * 1024 * 1024)
    with pytest.raises(ValueError, match="byte limit"):
        validate_probe(
            probe,
            mode="draft",
            max_seconds=300,
            max_bytes=50 * 1024 * 1024,
        )
