from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_verifier() -> ModuleType:
    path = PROJECT_ROOT / "scripts/verify_reported_results.py"
    spec = importlib.util.spec_from_file_location("askdu_test_reported_results", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load reported-results verifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFIER = load_verifier()


def test_current_paper_claims_match_the_verified_mechanism() -> None:
    failures: list[str] = []

    VERIFIER.verify_paper(failures, PROJECT_ROOT / "paper/main.tex")

    assert failures == []


def test_paper_verifier_rejects_unimplemented_preparation_target(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "main.tex"
    current = (PROJECT_ROOT / "paper/main.tex").read_text(encoding="utf-8")
    paper.write_text(
        current + "\nA typed repair goal can reopen Discovery or Preparation.\n",
        encoding="utf-8",
    )
    failures: list[str] = []

    VERIFIER.verify_paper(failures, paper)

    assert any("exceeds the implemented" in failure for failure in failures)
