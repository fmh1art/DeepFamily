from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = PROJECT_ROOT / "artifacts/demo/fallback-walkthrough.mp4"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/demo/submission-walkthrough.mp4"
CHECKER = PROJECT_ROOT / "scripts/check_demo_video.py"
PROVISIONAL_MAX_SECONDS = 300.0
PROVISIONAL_MAX_BYTES = 50 * 1024 * 1024


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def as_sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    return value


def probe_media(path: Path) -> Mapping[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe is required (normally installed with ffmpeg)")
    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return as_mapping(json.loads(process.stdout), f"ffprobe output for {path.name}")


def media_duration(probe: Mapping[str, Any], label: str) -> float:
    format_info = as_mapping(probe.get("format"), f"{label}.format")
    duration = float(format_info.get("duration", 0))
    require(duration > 0, f"{label} duration is unavailable")
    return duration


def stream_count(probe: Mapping[str, Any], codec_type: str) -> int:
    streams = as_sequence(probe.get("streams"), "probe.streams")
    return sum(
        1
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == codec_type
    )


def validate_inputs(
    video: Path,
    narration: Path,
    output: Path,
    *,
    minimum_fraction: float,
    max_overrun_seconds: float,
) -> tuple[float, float]:
    require(video.is_file(), f"base video does not exist: {video}")
    require(narration.is_file(), f"narration does not exist: {narration}")
    require(
        output.suffix.lower() == ".mp4", "submission output must use an .mp4 suffix"
    )
    require(output not in {video, narration}, "output must differ from both inputs")
    require(0 < minimum_fraction <= 1, "minimum narration fraction must be in (0, 1]")
    require(max_overrun_seconds >= 0, "maximum narration overrun must be non-negative")

    video_probe = probe_media(video)
    narration_probe = probe_media(narration)
    require(
        stream_count(video_probe, "video") == 1, "base video must have one video stream"
    )
    require(
        stream_count(narration_probe, "audio") == 1,
        "narration input must have exactly one audio stream",
    )
    video_duration = media_duration(video_probe, "base video")
    narration_duration = media_duration(narration_probe, "narration")
    require(
        narration_duration >= video_duration * minimum_fraction,
        "narration is too short for the walkthrough; export an audio track spanning the timeline",
    )
    require(
        narration_duration <= video_duration + max_overrun_seconds,
        "narration overruns the video and would be truncated",
    )
    return video_duration, narration_duration


def mux(
    video: Path,
    narration: Path,
    output: Path,
    *,
    max_seconds: float,
    max_bytes: int,
) -> tuple[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to encode narration")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".askdu-narrated-",
        suffix=".mp4",
        dir=output.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "warning",
                "-i",
                str(video),
                "-i",
                str(narration),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-strict",
                "-2",
                "-b:a",
                "128k",
                "-ar",
                "48000",
                "-af",
                "apad",
                "-shortest",
                "-movflags",
                "+faststart",
                "-map_metadata",
                "0",
                "-metadata",
                "title=Ask, Don't Upload — Narrated Demonstration",
                str(temporary),
            ],
            check=True,
            timeout=180,
        )
        checked = subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--mode",
                "submission",
                "--max-seconds",
                str(max_seconds),
                "--max-bytes",
                str(max_bytes),
                str(temporary),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if checked.returncode != 0:
            detail = (
                checked.stderr.strip() or checked.stdout.strip() or "unknown failure"
            )
            raise ValueError(f"muxed video failed the submission media gate: {detail}")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return checked.stdout, output.as_posix()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mux a human narration track into the checked demo walkthrough."
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--narration", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-fraction", type=float, default=0.6)
    parser.add_argument("--max-overrun-seconds", type=float, default=0.5)
    parser.add_argument("--max-seconds", type=float, default=PROVISIONAL_MAX_SECONDS)
    parser.add_argument("--max-bytes", type=int, default=PROVISIONAL_MAX_BYTES)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    video = args.video.expanduser().resolve()
    narration = args.narration.expanduser().resolve()
    output = args.output.expanduser().resolve()
    video_duration, narration_duration = validate_inputs(
        video,
        narration,
        output,
        minimum_fraction=args.minimum_fraction,
        max_overrun_seconds=args.max_overrun_seconds,
    )
    require(
        args.max_seconds > 0 and args.max_bytes > 0, "media limits must be positive"
    )
    checker_output, output_label = mux(
        video,
        narration,
        output,
        max_seconds=args.max_seconds,
        max_bytes=args.max_bytes,
    )
    print(
        f"Muxed {narration_duration:.2f}s narration across a {video_duration:.2f}s walkthrough."
    )
    print(checker_output.rstrip())
    print(f"Created {output_label}")


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"Narration mux failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
