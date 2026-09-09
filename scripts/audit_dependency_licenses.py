from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = (
    PROJECT_ROOT / "experiments/evidence/dependency-license-inventory-v0.4.0.json"
)
PUBLIC_NOTICE = (
    PROJECT_ROOT / "frontend/public/notices/dependency-license-inventory-v0.4.0.json"
)
DEFAULT_BACKEND_IMAGE = "ask-dont-upload-api"
DEFAULT_WEB_IMAGE = "ask-dont-upload-web"
FIRST_PARTY_PACKAGES = {"ask-dont-upload"}
RECIPROCAL_MARKERS = ("AGPL", "GPL", "LGPL", "MPL", "EPL", "CDDL")
COMPOUND_MARKERS = (" AND ", " OR ", "DUAL LICENSE", "CUSTOM")

BACKEND_INSPECTOR = r"""
import importlib.metadata as metadata
import json
import pathlib
import platform
import subprocess

def text(value):
    return str(value or "").strip()

def package_record(distribution):
    fields = distribution.metadata
    expression = text(fields.get("License-Expression"))
    license_text = text(fields.get("License"))
    classifiers = sorted(
        item.removeprefix("License :: OSI Approved :: ")
        for item in (fields.get_all("Classifier") or [])
        if item.startswith("License :: OSI Approved :: ")
    )
    if expression:
        license_value = expression
        license_source = "License-Expression"
    elif license_text and "\n" not in license_text and len(license_text) <= 160:
        license_value = license_text
        license_source = "License"
    elif classifiers:
        license_value = " | ".join(classifiers)
        license_source = "Classifier"
    else:
        license_value = ""
        license_source = "missing"
    return {
        "name": text(fields.get("Name")) or distribution.name,
        "version": distribution.version,
        "license": license_value,
        "license_source": license_source,
        "license_classifiers": classifiers,
        "license_files": sorted(fields.get_all("License-File") or []),
    }

installed = subprocess.check_output(
    ["dpkg-query", "-W", "-f=${binary:Package}\\t${Version}\\n"],
    text=True,
)
os_packages = []
for row in installed.splitlines():
    name, version = row.split("\t", 1)
    notice = pathlib.Path("/usr/share/doc") / name.split(":", 1)[0] / "copyright"
    os_packages.append(
        {
            "name": name,
            "version": version,
            "copyright_file_present": notice.exists(),
        }
    )

payload = {
    "python_version": platform.python_version(),
    "python_packages": sorted(
        (package_record(item) for item in metadata.distributions()),
        key=lambda item: item["name"].lower(),
    ),
    "os_packages": sorted(os_packages, key=lambda item: item["name"]),
}
print(json.dumps(payload, sort_keys=True))
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory application licenses from production images and lockfiles, "
            "then compare them with checked evidence."
        )
    )
    parser.add_argument("--expected", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--backend-image", default=DEFAULT_BACKEND_IMAGE)
    parser.add_argument("--web-image", default=DEFAULT_WEB_IMAGE)
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--print",
        action="store_true",
        dest="print_inventory",
        help="print current deterministic JSON instead of comparing it",
    )
    output_group.add_argument(
        "--write",
        action="store_true",
        dest="write_inventory",
        help="write current deterministic JSON to the evidence and public notice paths",
    )
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def docker_capture(arguments: list[str], *, timeout: int = 120) -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker is required for production-image inspection")
    process = subprocess.run(
        [docker, "run", "--rm", "--network", "none", *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return process.stdout


def inspect_backend(image: str) -> dict[str, Any]:
    output = docker_capture(["--entrypoint", "python", image, "-c", BACKEND_INSPECTOR])
    decoded = json.loads(output)
    if not isinstance(decoded, dict):
        raise TypeError("backend inspector did not return a JSON object")
    return decoded


def parse_apk_database(contents: str) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    for block in contents.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if len(line) >= 3 and line[1] == ":" and line[0] in {"P", "V", "L"}:
                fields[line[0]] = line[2:]
        if "P" not in fields:
            continue
        packages.append(
            {
                "name": fields["P"],
                "version": fields.get("V", ""),
                "license": fields.get("L", ""),
            }
        )
    return sorted(packages, key=lambda item: item["name"])


def inspect_alpine(image: str) -> list[dict[str, str]]:
    contents = docker_capture(
        ["--user", "0", "--entrypoint", "cat", image, "/lib/apk/db/installed"]
    )
    return parse_apk_database(contents)


def frontend_production_packages(lock_path: Path) -> list[dict[str, str]]:
    decoded = json.loads(lock_path.read_text(encoding="utf-8"))
    require(isinstance(decoded, dict), "frontend lockfile must contain an object")
    packages = decoded.get("packages")
    require(isinstance(packages, dict), "frontend lockfile has no packages map")
    result: list[dict[str, str]] = []
    for path, record in packages.items():
        if not path or not path.startswith("node_modules/"):
            continue
        require(isinstance(record, dict), f"invalid lock record for {path}")
        if record.get("dev") is True:
            continue
        name = path.rsplit("node_modules/", 1)[-1]
        result.append(
            {
                "name": name,
                "version": str(record.get("version", "")),
                "license": str(record.get("license", "")),
            }
        )
    return sorted(result, key=lambda item: item["name"].lower())


def dockerfile_base_images(path: Path) -> list[str]:
    images: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        words = line.split()
        if words and words[0].upper() == "FROM" and len(words) >= 2:
            images.append(words[1])
    return images


def review_reasons(
    license_value: str, classifiers: list[str] | None = None
) -> list[str]:
    normalized = license_value.upper()
    reasons: list[str] = []
    if any(marker in normalized for marker in RECIPROCAL_MARKERS):
        reasons.append("reciprocal-license identifier")
    if any(marker in normalized for marker in COMPOUND_MARKERS):
        reasons.append("compound or non-standard license metadata")
    if classifiers is not None and len(classifiers) > 1:
        reasons.append("multiple OSI license classifiers")
    return reasons


def application_review(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review: list[dict[str, Any]] = []
    for package in packages:
        reasons = review_reasons(
            str(package["license"]),
            [str(value) for value in package.get("license_classifiers", [])],
        )
        if reasons:
            review.append({"name": package["name"], "reasons": reasons})
    return review


def build_evidence(backend_image: str, web_image: str) -> dict[str, Any]:
    backend = inspect_backend(backend_image)
    python_packages = backend.get("python_packages")
    debian_packages = backend.get("os_packages")
    require(isinstance(python_packages, list), "backend package inventory is missing")
    require(isinstance(debian_packages, list), "Debian package inventory is missing")

    first_party = [
        package
        for package in python_packages
        if str(package.get("name", "")).lower() in FIRST_PARTY_PACKAGES
    ]
    third_party = [package for package in python_packages if package not in first_party]
    frontend_packages = frontend_production_packages(
        PROJECT_ROOT / "frontend/package-lock.json"
    )
    alpine_packages = inspect_alpine(web_image)

    evidence: dict[str, Any] = {
        "schema_version": "1.0",
        "project_version": "0.4.0",
        "scope": {
            "application_dependencies": "license-metadata completeness and drift",
            "container_os_packages": "inventory only; no legal compatibility conclusion",
            "build_only_dependencies": "excluded unless shipped in the final image",
            "legal_advice": False,
        },
        "inputs": {
            "backend_image": backend_image,
            "backend_base_images": dockerfile_base_images(
                PROJECT_ROOT / "backend/Dockerfile"
            ),
            "backend_dockerfile_sha256": sha256_file(
                PROJECT_ROOT / "backend/Dockerfile"
            ),
            "backend_lock_sha256": sha256_file(PROJECT_ROOT / "backend/uv.lock"),
            "web_image": web_image,
            "web_base_images": dockerfile_base_images(
                PROJECT_ROOT / "frontend/Dockerfile"
            ),
            "web_dockerfile_sha256": sha256_file(PROJECT_ROOT / "frontend/Dockerfile"),
            "frontend_lock_sha256": sha256_file(
                PROJECT_ROOT / "frontend/package-lock.json"
            ),
        },
        "backend_application": {
            "python_version": backend.get("python_version"),
            "first_party_packages": first_party,
            "third_party_package_count": len(third_party),
            "third_party_packages": third_party,
            "manual_review": application_review(third_party),
        },
        "frontend_application": {
            "production_package_count": len(frontend_packages),
            "production_packages": frontend_packages,
            "manual_review": application_review(frontend_packages),
        },
        "container_os_inventory": {
            "backend": {
                "ecosystem": "Debian dpkg",
                "package_count": len(debian_packages),
                "packages": debian_packages,
                "review_status": (
                    "inventory-only; Debian copyright files located but licenses not "
                    "normalized"
                ),
            },
            "web": {
                "ecosystem": "Alpine apk",
                "package_count": len(alpine_packages),
                "packages": alpine_packages,
                "manual_review": application_review(alpine_packages),
                "review_status": "inventory-only; machine-readable labels need legal review",
            },
        },
        "release_gates": {
            "root_project_license_present": any(
                (PROJECT_ROOT / name).is_file() for name in ("LICENSE", "LICENSE.txt")
            ),
            "application_license_metadata_complete": all(
                str(package.get("license", "")).strip()
                for package in [*third_party, *frontend_packages]
            ),
            "debian_copyright_files_present": all(
                package.get("copyright_file_present") is True
                for package in debian_packages
            ),
            "alpine_license_metadata_complete": all(
                package.get("license", "") for package in alpine_packages
            ),
            "container_os_legal_review_complete": False,
        },
    }
    validate_evidence(evidence)
    return evidence


def validate_evidence(evidence: dict[str, Any]) -> None:
    require(evidence.get("schema_version") == "1.0", "unexpected evidence schema")
    backend = evidence.get("backend_application")
    frontend = evidence.get("frontend_application")
    os_inventory = evidence.get("container_os_inventory")
    gates = evidence.get("release_gates")
    require(isinstance(backend, dict), "missing backend application inventory")
    require(isinstance(frontend, dict), "missing frontend application inventory")
    require(isinstance(os_inventory, dict), "missing container OS inventory")
    require(isinstance(gates, dict), "missing release gates")

    backend_packages = backend.get("third_party_packages")
    frontend_packages = frontend.get("production_packages")
    require(isinstance(backend_packages, list), "missing backend third-party packages")
    require(isinstance(frontend_packages, list), "missing frontend production packages")
    require(
        backend.get("third_party_package_count") == len(backend_packages),
        "backend package count mismatch",
    )
    require(
        frontend.get("production_package_count") == len(frontend_packages),
        "frontend package count mismatch",
    )
    require(bool(backend_packages), "backend dependency inventory is empty")
    require(bool(frontend_packages), "frontend dependency inventory is empty")
    application_packages = [*backend_packages, *frontend_packages]
    application_complete = all(
        isinstance(package, dict)
        and str(package.get("name", "")).strip()
        and str(package.get("version", "")).strip()
        and str(package.get("license", "")).strip()
        for package in application_packages
    )
    require(
        application_complete,
        "application dependency license metadata is incomplete",
    )
    require(
        gates.get("application_license_metadata_complete") is application_complete,
        "application license gate does not match the package records",
    )
    backend_os = os_inventory.get("backend")
    web_os = os_inventory.get("web")
    require(isinstance(backend_os, dict), "missing backend OS inventory")
    require(isinstance(web_os, dict), "missing web OS inventory")
    backend_os_packages = backend_os.get("packages")
    web_os_packages = web_os.get("packages")
    require(isinstance(backend_os_packages, list), "missing backend OS packages")
    require(isinstance(web_os_packages, list), "missing web OS packages")
    debian_notices_complete = bool(backend_os_packages) and all(
        isinstance(package, dict)
        and str(package.get("name", "")).strip()
        and str(package.get("version", "")).strip()
        and package.get("copyright_file_present") is True
        for package in backend_os_packages
    )
    alpine_metadata_complete = bool(web_os_packages) and all(
        isinstance(package, dict)
        and str(package.get("name", "")).strip()
        and str(package.get("version", "")).strip()
        and str(package.get("license", "")).strip()
        for package in web_os_packages
    )
    require(
        debian_notices_complete,
        "a Debian package lacks its installed copyright file",
    )
    require(
        gates.get("debian_copyright_files_present") is debian_notices_complete,
        "Debian notice gate does not match the package records",
    )
    require(
        alpine_metadata_complete,
        "an Alpine package lacks machine-readable license metadata",
    )
    require(
        gates.get("alpine_license_metadata_complete") is alpine_metadata_complete,
        "Alpine metadata gate does not match the package records",
    )
    for label in ("backend", "web"):
        inventory = os_inventory.get(label)
        require(isinstance(inventory, dict), f"missing {label} OS inventory")
        packages = inventory.get("packages")
        require(isinstance(packages, list), f"missing {label} OS packages")
        require(
            inventory.get("package_count") == len(packages), f"{label} count mismatch"
        )


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def compare_evidence(actual: dict[str, Any], expected_path: Path) -> None:
    if not expected_path.is_file():
        raise FileNotFoundError(f"checked evidence does not exist: {expected_path}")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    require(isinstance(expected, dict), "checked evidence must contain a JSON object")
    validate_evidence(expected)
    actual_text = canonical_json(actual)
    expected_text = canonical_json(expected)
    if actual_text == expected_text:
        if not PUBLIC_NOTICE.is_file():
            raise FileNotFoundError(
                f"public dependency notice does not exist: {PUBLIC_NOTICE}"
            )
        public_notice = json.loads(PUBLIC_NOTICE.read_text(encoding="utf-8"))
        require(
            public_notice == expected,
            "public dependency notice differs from checked evidence",
        )
        return
    diff = "".join(
        difflib.unified_diff(
            expected_text.splitlines(keepends=True),
            actual_text.splitlines(keepends=True),
            fromfile=str(expected_path),
            tofile="current production inventory",
            n=3,
        )
    )
    raise ValueError(f"dependency-license evidence drifted:\n{diff}")


def write_evidence(actual: dict[str, Any], expected_path: Path) -> None:
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_NOTICE.parent.mkdir(parents=True, exist_ok=True)
    contents = canonical_json(actual)
    expected_path.write_text(contents, encoding="utf-8")
    PUBLIC_NOTICE.write_text(contents, encoding="utf-8")


def main() -> None:
    args = parse_args()
    try:
        evidence = build_evidence(args.backend_image, args.web_image)
        if args.print_inventory:
            print(canonical_json(evidence), end="")
            return
        expected_path = args.expected.expanduser().resolve()
        if args.write_inventory:
            write_evidence(evidence, expected_path)
            print(f"WROTE: {expected_path}")
            print(f"WROTE: {PUBLIC_NOTICE}")
            print(
                "INFO: writing inventory does not complete the manual OS legal review gate."
            )
            return
        compare_evidence(evidence, expected_path)
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"Dependency-license audit failed: {exc}") from exc

    backend_count = evidence["backend_application"]["third_party_package_count"]
    frontend_count = evidence["frontend_application"]["production_package_count"]
    debian_count = evidence["container_os_inventory"]["backend"]["package_count"]
    alpine_count = evidence["container_os_inventory"]["web"]["package_count"]
    print(
        "PASS: production inventory matches checked evidence "
        f"({backend_count} Python, {frontend_count} frontend, "
        f"{debian_count} Debian, {alpine_count} Alpine packages)."
    )
    print("INFO: container OS license compatibility remains an explicit manual gate.")


if __name__ == "__main__":
    main()
