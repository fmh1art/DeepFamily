from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = PROJECT_ROOT / "artifacts/demo/fallback-walkthrough.mp4"
PROVISIONAL_MAX_SECONDS = 300.0
PROVISIONAL_MAX_BYTES = 50 * 1024 * 1024
MIN_NARRATION_MEAN_DB = -50.0
MIN_NARRATION_PEAK_DB = -30.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check the technical properties of a generated demo video."
    )
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--mode", choices=("draft", "submission"), default="draft")
    parser.add_argument("--max-seconds", type=float, default=PROVISIONAL_MAX_SECONDS)
    parser.add_argument("--max-bytes", type=int, default=PROVISIONAL_MAX_BYTES)
    args = parser.parse_args()
    if args.max_seconds <= 0 or args.max_bytes <= 0:
        parser.error("media limits must be positive")
    return args


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_probe(
    probe: dict[str, Any],
    *,
    mode: str,
    max_seconds: float,
    max_bytes: int,
) -> dict[str, Any]:
    streams = probe.get("streams")
    format_info = probe.get("format")
    require(isinstance(streams, list), "ffprobe returned no stream list")
    require(isinstance(format_info, dict), "ffprobe returned no format object")
    video_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "video"
    ]
    audio_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    ]
    require(len(video_streams) == 1, "video must contain exactly one video stream")
    video = video_streams[0]
    container_formats = str(format_info.get("format_name", "")).split(",")
    require("mp4" in container_formats, "video container must be MP4")
    require(video.get("codec_name") == "h264", "video codec must be H.264")
    require(
        (video.get("width"), video.get("height")) == (1600, 900),
        "video dimensions must be 1600x900",
    )
    require(video.get("pix_fmt") == "yuv420p", "pixel format must be yuv420p")

    duration = float(format_info.get("duration", 0))
    size = int(format_info.get("size", 0))
    require(duration >= 10, "video is too short to contain the walkthrough")
    require(duration <= max_seconds, f"video exceeds the {max_seconds:g}-second limit")
    require(size > 0, "video file is empty")
    require(size <= max_bytes, f"video exceeds the {max_bytes}-byte limit")
    if mode == "submission":
        require(
            len(audio_streams) == 1,
            "submission video must contain exactly one narration stream",
        )
        audio = audio_streams[0]
        require(
            audio.get("codec_name") == "aac",
            "submission narration must use AAC",
        )
        sample_rate = int(audio.get("sample_rate", 0))
        channels = int(audio.get("channels", 0))
        audio_duration = float(audio.get("duration", 0))
        require(
            sample_rate >= 44_100, "narration sample rate must be at least 44.1 kHz"
        )
        require(channels in {1, 2}, "narration must be mono or stereo")
        require(
            audio_duration >= duration - 1.0,
            "narration stream must cover the walkthrough timeline",
        )

    summary = {
        "duration_seconds": round(duration, 3),
        "size_bytes": size,
        "container": "mp4",
        "video_codec": video.get("codec_name"),
        "dimensions": f"{video.get('width')}x{video.get('height')}",
        "pixel_format": video.get("pix_fmt"),
        "frame_rate": video.get("r_frame_rate"),
        "audio_streams": len(audio_streams),
        "mode": mode,
    }
    if audio_streams:
        audio = audio_streams[0]
        summary.update(
            {
                "audio_codec": audio.get("codec_name"),
                "audio_sample_rate_hz": int(audio.get("sample_rate", 0)),
                "audio_channels": int(audio.get("channels", 0)),
                "audio_duration_seconds": round(float(audio.get("duration", 0)), 3),
            }
        )
    return summary


def probe_video(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe is required (normally installed with ffmpeg)")
    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            (
                "format=format_name,duration,size:"
                "stream=codec_type,codec_name,width,height,pix_fmt,r_frame_rate,"
                "sample_rate,channels,duration"
            ),
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    decoded = json.loads(process.stdout)
    if not isinstance(decoded, dict):
        raise TypeError("ffprobe output must be a JSON object")
    return decoded


def probe_audio_levels(path: Path) -> dict[str, float]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to validate narration levels")
    process = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    levels: dict[str, float] = {}
    for name in ("mean_volume", "max_volume"):
        match = re.search(rf"{name}:\s*(-?(?:inf|\d+(?:\.\d+)?))\s+dB", process.stderr)
        if match is None:
            raise RuntimeError(f"ffmpeg did not report {name}")
        levels[f"{name}_db"] = float(match.group(1))
    return levels


def validate_audio_levels(levels: dict[str, float]) -> None:
    mean_volume = levels["mean_volume_db"]
    max_volume = levels["max_volume_db"]
    require(
        math.isfinite(mean_volume) and mean_volume >= MIN_NARRATION_MEAN_DB,
        f"narration mean level must be at least {MIN_NARRATION_MEAN_DB:g} dB",
    )
    require(
        math.isfinite(max_volume) and max_volume >= MIN_NARRATION_PEAK_DB,
        f"narration peak level must be at least {MIN_NARRATION_PEAK_DB:g} dB",
    )
    require(mean_volume <= max_volume <= 0, "narration level measurements are invalid")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    path = args.path.expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"video does not exist: {path}")
    try:
        summary = validate_probe(
            probe_video(path),
            mode=args.mode,
            max_seconds=args.max_seconds,
            max_bytes=args.max_bytes,
        )
        if args.mode == "submission":
            levels = probe_audio_levels(path)
            validate_audio_levels(levels)
            summary.update(levels)
    except (OSError, subprocess.SubprocessError, TypeError, ValueError) as exc:
        raise SystemExit(f"Video check failed: {exc}") from exc

    print(json.dumps(summary, indent=2))
    print(f"SHA-256: {sha256_file(path)}")
    if args.mode == "draft" and summary["audio_streams"] == 0:
        print("INFO: draft is silent; submission mode will require AAC narration.")
    print("PASS: demo video satisfies the configured technical media gate.")


if __name__ == "__main__":
    main()
