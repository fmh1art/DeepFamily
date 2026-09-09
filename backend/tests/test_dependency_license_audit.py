from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE: dict[str, Any] = runpy.run_path(str(PROJECT_ROOT / "scripts/audit_dependency_licenses.py"))


def test_frontend_inventory_excludes_development_dependencies(tmp_path: Path) -> None:
    frontend_production_packages = MODULE["frontend_production_packages"]
    lock = {
        "packages": {
            "": {"dependencies": {"react": "1"}},
            "node_modules/react": {"version": "1.0.0", "license": "MIT"},
            "node_modules/test-only": {
                "version": "2.0.0",
                "license": "ISC",
                "dev": True,
            },
        }
    }
    lock_path = tmp_path / "package-lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    assert frontend_production_packages(lock_path) == [
        {"name": "react", "version": "1.0.0", "license": "MIT"}
    ]


def test_apk_database_parser_preserves_compound_license_labels() -> None:
    parse_apk_database = MODULE["parse_apk_database"]
    contents = """P:busybox
V:1.37-r0
L:GPL-2.0-only

P:ca-certificates
V:1-r0
L:MPL-2.0 AND MIT
"""

    assert parse_apk_database(contents) == [
        {"name": "busybox", "version": "1.37-r0", "license": "GPL-2.0-only"},
        {
            "name": "ca-certificates",
            "version": "1-r0",
            "license": "MPL-2.0 AND MIT",
        },
    ]


def test_review_triage_is_descriptive_not_a_compatibility_decision() -> None:
    review_reasons = MODULE["review_reasons"]

    assert review_reasons("MIT") == []
    assert review_reasons("MPL-2.0 AND MIT") == [
        "reciprocal-license identifier",
        "compound or non-standard license metadata",
    ]
    assert review_reasons("Dual License", ["Apache Software License", "BSD License"]) == [
        "compound or non-standard license metadata",
        "multiple OSI license classifiers",
    ]


def test_checked_evidence_rejects_missing_application_license() -> None:
    validate_evidence = MODULE["validate_evidence"]
    evidence = {
        "schema_version": "1.0",
        "backend_application": {
            "third_party_package_count": 1,
            "third_party_packages": [{"name": "x", "license": ""}],
        },
        "frontend_application": {
            "production_package_count": 1,
            "production_packages": [{"name": "y", "license": "MIT"}],
        },
        "container_os_inventory": {
            "backend": {"package_count": 1, "packages": [{}]},
            "web": {"package_count": 1, "packages": [{}]},
        },
        "release_gates": {
            "application_license_metadata_complete": True,
            "debian_copyright_files_present": True,
            "alpine_license_metadata_complete": True,
        },
    }

    with pytest.raises(ValueError, match="license metadata is incomplete"):
        validate_evidence(evidence)


def test_versioned_inventory_is_internally_valid_and_pinned_to_inputs() -> None:
    validate_evidence = MODULE["validate_evidence"]
    sha256_file = MODULE["sha256_file"]
    evidence_path = PROJECT_ROOT / "experiments/evidence/dependency-license-inventory-v0.4.0.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    public_notice_path = (
        PROJECT_ROOT / "frontend/public/notices/dependency-license-inventory-v0.4.0.json"
    )

    validate_evidence(evidence)
    assert public_notice_path.read_bytes() == evidence_path.read_bytes()
    assert evidence["backend_application"]["third_party_package_count"] == 45
    assert evidence["frontend_application"]["production_package_count"] == 3
    assert evidence["container_os_inventory"]["backend"]["package_count"] == 105
    assert evidence["container_os_inventory"]["web"]["package_count"] == 21
    assert evidence["inputs"]["backend_dockerfile_sha256"] == sha256_file(
        PROJECT_ROOT / "backend/Dockerfile"
    )
    assert evidence["inputs"]["backend_lock_sha256"] == sha256_file(
        PROJECT_ROOT / "backend/uv.lock"
    )
    assert evidence["inputs"]["web_dockerfile_sha256"] == sha256_file(
        PROJECT_ROOT / "frontend/Dockerfile"
    )
    assert evidence["inputs"]["frontend_lock_sha256"] == sha256_file(
        PROJECT_ROOT / "frontend/package-lock.json"
    )
