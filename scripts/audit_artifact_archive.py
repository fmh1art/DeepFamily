"""Inspect the actual bundle, without extracting or executing its contents.

The credential check is a conservative assignment heuristic, not a complete
secret detector. Public release still requires the separate author/legal gates.
"""

from __future__ import annotations

import argparse
import re
import tarfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

PREVIEW_PROVIDER = (
    "https://aidp.bytedance.net/api/modelhub/online/v2/crawl"
    "?api-version=2024-03-01-preview"
)
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 10_000
CREDENTIAL = re.compile(
    rb"(?:api[_-]?key|secret|token)[\"']?[ \t]*[:=][ \t]*[\"']?[A-Za-z0-9+/=_-]{24,}",
    re.IGNORECASE,
)
# Include shell/Compose defaults as well as direct environment assignments.
PROVIDER_ASSIGNMENT = re.compile(
    r"ASKDU_LLM_(?:BASE_URL|ENDPOINT)\s*(?::[-=]|[:=])\s*[\"']?"
    r"(https?://[^\s\"'`<>}]+)"
)
FORBIDDEN_COMPONENTS = {
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "test-results",
    "playwright-report",
    "supported_research_paper",
    "runtime",
    "artifacts",
}
FORBIDDEN_PATHS = {
    "data/pilots/heldout-v1-questions.json",
    "data/manifests/coda-community-45-extracted.sha256",
    "paper/main.pdf",
    "paper/main.build.json",
    "paper/acmart.cls",
    "paper/pvldb.sty",
    "paper/ACM-Reference-Format.bst",
}


class ArtifactAuditError(ValueError):
    pass


def allowed_provider(url: str, *, mode: str) -> bool:
    if mode == "preview" and url == PREVIEW_PROVIDER:
        return True
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        return (
            parsed.scheme in {"http", "https"}
            and not parsed.username
            and not parsed.password
            and (host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".example"))
        )
    except ValueError:
        return False


def audit_archive(archive: Path, *, expected_root: str, mode: str) -> int:
    if mode not in {"preview", "public"}:
        raise ArtifactAuditError("unknown archive mode")
    if not re.fullmatch(r"ask-dont-upload-v[0-9][A-Za-z0-9.+-]*", expected_root):
        raise ArtifactAuditError("invalid expected archive root")
    seen: set[str] = set()
    total_bytes = 0
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            name = member.name.rstrip("/")
            parts = name.split("/")
            if (
                not name
                or parts[0] != expected_root
                or any(part in {"", ".", ".."} for part in parts)
                or "\\" in name
                or any(ord(char) < 32 or ord(char) == 127 for char in name)
            ):
                raise ArtifactAuditError("unsafe member path")
            if name in seen:
                raise ArtifactAuditError("duplicate member path")
            seen.add(name)
            if len(seen) > MAX_MEMBERS:
                raise ArtifactAuditError("too many archive members")
            if not (member.isfile() or member.isdir()) or member.issparse():
                raise ArtifactAuditError(
                    "links, sparse files or special members are forbidden"
                )
            relative = PurePosixPath(*parts[1:]).as_posix()
            if (
                any(part in FORBIDDEN_COMPONENTS for part in parts[1:])
                or relative in FORBIDDEN_PATHS
                or relative.startswith(("data/external/", "experiments/results/"))
                or relative in {"data/external", "experiments/results"}
                or (
                    relative.startswith("third_party/")
                    and relative != "third_party/README.md"
                )
                or relative == "third_party"
            ):
                raise ArtifactAuditError(f"forbidden artifact member: {relative}")
            if relative != ".env.example" and any(
                part == ".env" or part.startswith(".env.") for part in parts[1:]
            ):
                raise ArtifactAuditError("private environment file in archive")
            total_bytes += member.size
            if (
                not 0 <= member.size <= MAX_MEMBER_BYTES
                or total_bytes > MAX_TOTAL_BYTES
            ):
                raise ArtifactAuditError("archive exceeds the inspection size limit")
            if not member.isfile():
                continue
            stream = bundle.extractfile(member)
            if stream is None:
                raise ArtifactAuditError("could not read archive member")
            with stream:
                content = stream.read()
            if CREDENTIAL.search(content):
                # Never print the matched value or a line containing it.
                raise ArtifactAuditError(f"credential-shaped assignment in: {relative}")
            for match in PROVIDER_ASSIGNMENT.finditer(
                content.decode("utf-8", errors="replace")
            ):
                if not allowed_provider(match[1], mode=mode):
                    raise ArtifactAuditError(
                        f"concrete model-provider configuration in: {relative}"
                    )
    if not seen:
        raise ArtifactAuditError("empty archive")
    return len(seen)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expected-root", required=True)
    parser.add_argument("--mode", choices=("preview", "public"), required=True)
    args = parser.parse_args()
    try:
        count = audit_archive(
            args.archive, expected_root=args.expected_root, mode=args.mode
        )
    except (ArtifactAuditError, OSError, tarfile.TarError, EOFError) as exc:
        # Library errors may contain archive bytes; only our controlled diagnostics are public.
        detail = (
            str(exc)
            if isinstance(exc, ArtifactAuditError)
            else "archive could not be read"
        )
        print(f"ERROR: artifact content audit failed: {detail}")
        return 1
    print(
        f"PASS: inspected {count} actual archive members ({args.mode} content policy)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
