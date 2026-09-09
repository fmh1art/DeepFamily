#!/usr/bin/env python3
"""Download, verify, and safely extract the pinned open CoDA-Bench release.

The manifest deliberately omits the sealed evaluation community. This command
therefore cannot download, list, or extract that environment.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"
sys.path.insert(0, str(BACKEND_SRC))

from askdu.adapters.coda_release import (
    CodaReleaseError,
    CodaReleaseRegistry,
    CommunityPin,
    FilePin,
    sha256_file,
)

DEFAULT_MANIFEST = PROJECT_ROOT / "data/manifests/coda-bench-v1-open-release.json"
DEFAULT_RELEASE_ROOT = PROJECT_ROOT / "data/external/coda-bench"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--all-open",
        action="store_true",
        help="synchronize every community admitted by the open-runtime manifest",
    )
    selection.add_argument(
        "--community",
        type=int,
        action="append",
        help="synchronize one open community; repeat the option for more than one",
    )
    selection.add_argument(
        "--metadata-only",
        action="store_true",
        help="download and verify benchmark metadata without any community archive",
    )
    selection.add_argument(
        "--status",
        action="store_true",
        help="show local installation status without network access",
    )
    parser.add_argument(
        "--download-only", action="store_true", help="do not extract archives"
    )
    parser.add_argument(
        "--verify-existing-archives",
        action="store_true",
        help="hash already-downloaded archives while reporting status",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="with --status, exit non-zero unless every admitted open community is extracted",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASE_ROOT)
    return parser.parse_args()


def resolve_command(name: str, extra_candidates: tuple[Path, ...] = ()) -> str:
    found = shutil.which(name)
    if found:
        return found
    match = next((str(path) for path in extra_candidates if path.is_file()), None)
    if match is None:
        raise CodaReleaseError(f"Required command is unavailable: {name}")
    return match


def direct_network_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        environment.pop(name, None)
    return environment


def run_download(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        print(
            "Initial download path failed; retrying without proxy variables.",
            file=sys.stderr,
        )
        subprocess.run(command, check=True, env=direct_network_environment())


def verify_file(root: Path, pin: FilePin) -> None:
    target = (root / pin.path).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise CodaReleaseError(f"Pinned file is missing: {pin.path}")
    actual_bytes = target.stat().st_size
    if actual_bytes != pin.bytes:
        raise CodaReleaseError(
            f"Pinned size mismatch for {pin.path}: expected {pin.bytes}, got {actual_bytes}"
        )
    actual_sha256 = sha256_file(target)
    if actual_sha256 != pin.sha256:
        raise CodaReleaseError(f"Pinned checksum mismatch for {pin.path}")
    print(f"Verified {pin.path} ({pin.bytes} bytes)")


def download_pin(
    *,
    hf: str,
    repository: str,
    repository_type: str,
    revision: str,
    release_root: Path,
    pin: FilePin,
) -> None:
    target = release_root / pin.path
    if target.is_file() and target.stat().st_size == pin.bytes:
        if sha256_file(target) == pin.sha256:
            print(f"Already verified {pin.path}")
            return
        raise CodaReleaseError(f"Existing file has the wrong checksum: {pin.path}")
    release_root.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {pin.path} ({pin.bytes} bytes)")
    run_download(
        [
            hf,
            "download",
            repository,
            pin.path,
            "--repo-type",
            repository_type,
            "--revision",
            revision,
            "--local-dir",
            str(release_root),
            "--max-workers",
            "2",
        ]
    )
    verify_file(release_root, pin)


def safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or ".." in path.parts:
        raise CodaReleaseError("Archive contains an unsafe member path")
    return path


def extract_stream(process: subprocess.Popen[bytes], staging: Path) -> tuple[int, int]:
    if process.stdout is None:  # pragma: no cover - subprocess invariant
        raise CodaReleaseError("Could not read zstd output")
    file_count = 0
    extracted_bytes = 0
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                relative = safe_member_path(member.name)
                destination = staging.joinpath(*relative.parts)
                resolved_parent = destination.parent.resolve()
                if not resolved_parent.is_relative_to(staging.resolve()):
                    raise CodaReleaseError(
                        "Archive member escaped the staging directory"
                    )
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise CodaReleaseError("Archive contains a link or special file")
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise CodaReleaseError("Archive member has no readable payload")
                with source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                file_count += 1
                extracted_bytes += member.size
                if file_count % 1000 == 0:
                    print(
                        f"  extracted {file_count} files / {extracted_bytes} bytes",
                        flush=True,
                    )
    finally:
        process.stdout.close()
    return file_count, extracted_bytes


def extract_community(*, zstd: str, release_root: Path, pin: CommunityPin) -> None:
    archive_path = (release_root / pin.path).resolve()
    target = release_root / "communities" / f"community_{pin.community_id}"
    if (target / "full_community").is_dir():
        print(f"Already extracted community {pin.community_id}")
        return
    if target.exists():
        raise CodaReleaseError(f"Incomplete extraction target already exists: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".community-{pin.community_id}-", dir=release_root)
    )
    print(f"Extracting community {pin.community_id}")
    process = subprocess.Popen([zstd, "-dc", str(archive_path)], stdout=subprocess.PIPE)
    try:
        file_count, extracted_bytes = extract_stream(process, staging)
        return_code = process.wait()
        if return_code != 0:
            raise CodaReleaseError(
                f"zstd failed while extracting community {pin.community_id}"
            )
        source = staging / "data" / f"community_{pin.community_id}"
        if not (source / "full_community").is_dir():
            raise CodaReleaseError("Archive has an unexpected CoDA community layout")
        source.replace(target)
        print(
            f"Installed community {pin.community_id}: "
            f"{file_count} files / {extracted_bytes} extracted bytes"
        )
    except BaseException:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def print_status(registry: CodaReleaseRegistry, *, verify_archives: bool) -> bool:
    installations = registry.installations(verify_archives=verify_archives)
    downloaded = sum(item.archive_downloaded for item in installations)
    verified = sum(item.archive_verified for item in installations)
    extracted = sum(item.extracted for item in installations)
    total = len(installations)
    print(f"Pinned release: {registry.manifest.revision}")
    print(f"Open communities: {total}")
    print(
        "Open runtime scope: "
        f"{registry.manifest.open_runtime.task_count} tasks / "
        f"{registry.manifest.open_runtime.source_dataset_count} source datasets / "
        f"{registry.manifest.open_runtime.compressed_archive_bytes} compressed bytes"
    )
    print(f"Archives downloaded: {downloaded}/{total}")
    if verify_archives:
        print(f"Archives verified: {verified}/{total}")
    print(f"Communities extracted: {extracted}/{total}")
    missing = [str(item.community_id) for item in installations if not item.extracted]
    if missing:
        print("Not extracted: " + ", ".join(missing))
    return not missing


def main() -> int:
    args = parse_args()
    registry = CodaReleaseRegistry(
        manifest_path=args.manifest,
        release_root=args.release_root,
    )
    if args.status:
        complete = print_status(
            registry,
            verify_archives=args.verify_existing_archives,
        )
        return 1 if args.require_complete and not complete else 0

    hf = resolve_command("hf")
    manifest = registry.manifest
    for pin in manifest.metadata:
        download_pin(
            hf=hf,
            repository=manifest.repository,
            repository_type=manifest.repository_type,
            revision=manifest.revision,
            release_root=registry.release_root,
            pin=pin,
        )
    if args.metadata_only:
        return 0

    community_ids = (
        [item.community_id for item in manifest.archives]
        if args.all_open
        else list(dict.fromkeys(args.community or []))
    )
    pins = [manifest.community(community_id) for community_id in community_ids]
    zstd = ""
    if not args.download_only:
        zstd = resolve_command(
            "zstd",
            (
                Path("/usr/bin/zstd"),
                Path("/usr/local/bin/zstd"),
                Path("/opt/homebrew/bin/zstd"),
                Path("/opt/tiger/ss_bin/zstd"),
            ),
        )
    for pin in pins:
        if not args.download_only and registry.installation(pin.community_id).extracted:
            print(f"Already installed community {pin.community_id}")
            continue
        download_pin(
            hf=hf,
            repository=manifest.repository,
            repository_type=manifest.repository_type,
            revision=manifest.revision,
            release_root=registry.release_root,
            pin=pin,
        )
        if not args.download_only:
            extract_community(zstd=zstd, release_root=registry.release_root, pin=pin)
    print_status(registry, verify_archives=False)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        CodaReleaseError,
        OSError,
        subprocess.SubprocessError,
        tarfile.TarError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
