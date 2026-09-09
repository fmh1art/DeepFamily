from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from askdu.domain import RunState, RunStatus
from deployment.repository import ManagedFileRunRepository


def terminal_state(*, hours_old: int) -> RunState:
    timestamp = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    return RunState(
        environment_id="test-community",
        question="How many records satisfy this sufficiently long analytical condition?",
        status=RunStatus.COMPLETED,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_prune_and_delete_remove_only_the_target_run_tree(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    run_root = tmp_path / "runs"
    repository = ManagedFileRunRepository(state_root, run_root)
    expired = terminal_state(hours_old=3)
    recent = terminal_state(hours_old=0)
    active = terminal_state(hours_old=3).model_copy(update={"status": RunStatus.RUNNING})
    repository.save(expired)
    repository.save(recent)
    repository.save(active)
    for state in (expired, recent, active):
        report = run_root / state.run_id / "reports" / "report.md"
        report.parent.mkdir(parents=True)
        report.write_text("verified report", encoding="utf-8")
    malformed = state_root / "run_0000000000000000.json"
    malformed.write_text("not-json", encoding="utf-8")

    deleted = repository.prune_before(datetime.now(timezone.utc) - timedelta(hours=1))

    assert deleted == [expired.run_id]
    assert repository.get(expired.run_id) is None
    assert not (run_root / expired.run_id).exists()
    assert repository.get(recent.run_id) is not None
    assert (run_root / recent.run_id / "reports" / "report.md").is_file()
    assert repository.get(active.run_id) is not None
    assert (run_root / active.run_id / "reports" / "report.md").is_file()
    assert malformed.is_file()

    assert repository.delete(recent.run_id) is True
    assert repository.delete(recent.run_id) is False
    assert repository.get(recent.run_id) is None
    assert not (run_root / recent.run_id).exists()


def test_delete_unlinks_a_run_directory_symlink_without_following_it(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    run_root = tmp_path / "runs"
    repository = ManagedFileRunRepository(state_root, run_root)
    state = terminal_state(hours_old=0)
    repository.save(state)
    outside = tmp_path / "outside"
    outside.mkdir()
    evidence = outside / "must-remain.txt"
    evidence.write_text("preserve", encoding="utf-8")
    (run_root / state.run_id).symlink_to(outside, target_is_directory=True)

    assert repository.delete(state.run_id) is True

    assert evidence.read_text(encoding="utf-8") == "preserve"
    assert not (run_root / state.run_id).exists()


def test_retention_cutoff_and_run_id_must_be_safe(tmp_path: Path) -> None:
    repository = ManagedFileRunRepository(tmp_path / "state", tmp_path / "runs")

    with pytest.raises(ValueError, match="timezone-aware"):
        repository.prune_before(datetime.now())
    with pytest.raises(ValueError, match="Invalid run identifier"):
        repository.delete("../another-run")
