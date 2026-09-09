from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

PILOT_QUESTION = (
    "What are the Pearson correlation coefficients between the number of students who took "
    "the SHSAT and the percentage of Asian, Black/Hispanic, and White students for Grade 8 "
    "in 2016, using SHSAT registration and tester data that includes grade level information?"
)
ECONOMIC_NEED_QUESTION = (
    "What is the final count of records available after filtering for the year 2016 and "
    "grade level 8, and removing rows where the 'Economic Need Index' is missing?"
)
OFFER_DEMOGRAPHICS_QUESTION = (
    "For schools where students received offers, what are the average percentages of "
    "Black/Hispanic, White, and Asian students?"
)

TEST_SOURCE_PROVENANCE = {
    "data_science_for_good": {
        "title": "Data Science for Good: PASSNYC",
        "provider": "Kaggle",
        "creator": "PASSNYC and collaborators",
        "source_url": "https://www.kaggle.com/datasets/passnyc/data-science-for-good",
        "license_label": "CC0-1.0",
        "license_status": "declared",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
    },
    "2017-2018-shsat-admissions-test-offers-by-schools": {
        "title": "2017-2018 SHSAT Admissions Test Offers by Schools",
        "provider": "Kaggle",
        "creator": "infocusp",
        "source_url": (
            "https://www.kaggle.com/datasets/infocusp/"
            "2017-2018-shsat-admissions-test-offers-by-schools"
        ),
        "license_label": "Unknown",
        "license_status": "unknown",
        "license_url": None,
    },
    "nyc-school-district-breakdowns": {
        "title": "School District Breakdowns",
        "provider": "NYC Open Data",
        "creator": "Department of Youth and Community Development (DYCD)",
        "source_url": "https://data.cityofnewyork.us/d/g3vh-kbnw",
        "license_label": "CC0-1.0 (mirror metadata)",
        "license_status": "declared",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
    },
}


def write_test_provenance_manifest(
    data_root: Path,
    output_dir: Path,
    *,
    tamper_relative_path: str | None = None,
) -> Path:
    """Write a self-contained audited-manifest fixture for the synthetic catalog."""

    relative_paths = sorted(
        path.relative_to(data_root).as_posix() for path in data_root.rglob("*.csv")
    )
    lines: list[str] = []
    for relative_path in relative_paths:
        digest = hashlib.sha256((data_root / relative_path).read_bytes()).hexdigest()
        if relative_path == tamper_relative_path:
            digest = "0" * 64
        lines.append(f"{digest}  communities/community_43/full_community/{relative_path}")
    checksum_payload = ("\n".join(lines) + "\n").encode()
    checksum_name = "test-community-43-csv.sha256"
    (output_dir / checksum_name).write_bytes(checksum_payload)

    source_keys = sorted({Path(relative_path).parts[0] for relative_path in relative_paths})
    manifest = {
        "schema_version": "1.0",
        "audit_date": "2026-09-06",
        "benchmark": {
            "name": "CoDA-Bench",
            "upstream_url": "https://huggingface.co/datasets/RUC-DataLab/CoDA-Bench",
            "revision": "63828a2b652e26a9770555a0cc41e6c8aafdb5d9",
        },
        "data_access_policy": "download_only",
        "source_data_bundled": False,
        "environments": {
            "coda-community-43": {
                "community_id": 43,
                "archive_sha256": "a" * 64,
                "archive_bytes": sum(
                    (data_root / relative_path).stat().st_size for relative_path in relative_paths
                ),
                "asset_manifest": f"data/manifests/{checksum_name}",
                "asset_manifest_sha256": hashlib.sha256(checksum_payload).hexdigest(),
                "csv_asset_count": len(relative_paths),
                "source_count": len(source_keys),
                "sources": {key: TEST_SOURCE_PROVENANCE[key] for key in source_keys},
            }
        },
    }
    manifest_path = output_dir / "test-provenance.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


@pytest.fixture()
def sample_environment(tmp_path: Path) -> Path:
    root = tmp_path / "community" / "full_community"
    registration_dir = root / "data_science_for_good" / "source"
    registration_dir.mkdir(parents=True)
    registration = pd.DataFrame(
        {
            "DBN": ["01A", "02B", "03C", "04D", "05E"],
            "School name": ["A", "B", "C", "D", "E"],
            "Year of SHST": [2016, 2016, 2016, 2016, 2015],
            "Grade level": [8, 8, 8, 8, 8],
            "Enrollment on 10/31": [100, 100, 100, 100, 100],
            "Number of students who registered for the SHSAT": [12, 22, 32, 42, 52],
            "Number of students who took the SHSAT": [10, 20, 30, 40, 50],
        }
    )
    registration.to_csv(
        registration_dir / "D5 SHSAT Registrations and Testers.csv",
        index=False,
    )
    schools = pd.DataFrame(
        {
            "Location Code": ["01A", "02B", "03C", "04D"],
            "School Name": ["A", "B", "C", "D"],
            "City": ["New York"] * 4,
            "Economic Need Index": [0.8, 0.7, 0.6, 0.5],
            "Percent Asian": ["10%", "20%", "30%", "40%"],
            "Percent Black / Hispanic": ["40%", "30%", "20%", "10%"],
            "Percent White": ["15%", "25%", "35%", "45%"],
        }
    )
    schools.to_csv(registration_dir / "2016 School Explorer.csv", index=False)

    offer_dir = root / "2017-2018-shsat-admissions-test-offers-by-schools" / "source"
    offer_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "School DBN": ["01A", "02B", "03C", "04D"],
            "School Category": ["Middle School"] * 4,
            "School Name": ["A", "B", "C", "D"],
            "Number of students who took test": [20, 30, 40, 50],
            "Number of students who received offer": [2, 3, 4, 5],
        }
    ).to_csv(
        offer_dir / "2017-2018 SHSAT Admissions Test Offers By Sending School.csv",
        index=False,
    )

    distractor_dir = root / "nyc-school-district-breakdowns" / "source"
    distractor_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "JURISDICTION NAME": ["District 1"],
            "COUNT PARTICIPANTS": [100],
            "PERCENT ASIAN NON HISPANIC": [12.0],
        }
    ).to_csv(distractor_dir / "school-district-breakdowns.csv", index=False)
    return root
