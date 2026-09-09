from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from askdu.adapters.repository import RUN_ID_PATTERN, FileRunRepository
from askdu.domain import RunState, RunStatus


class ManagedFileRunRepository(FileRunRepository):
    """Add bounded deletion to the core's atomic file repository."""

    def __init__(self, state_root: Path, run_root: Path):
        super().__init__(state_root)
        self.run_root = run_root.expanduser().resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)

    def delete(self, run_id: str) -> bool:
        """Delete one validated state and its generated run tree."""

        state_path = self._path_for(run_id)
        with self._lock:
            if not state_path.exists() or state_path.is_symlink():
                return False
            self._delete_locked(run_id, state_path)
            return True

    def prune_before(self, cutoff: datetime) -> list[str]:
        """Delete terminal states last updated before an aware cutoff."""

        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("Retention cutoff must be timezone-aware")
        deleted: list[str] = []
        with self._lock:
            for state_path in sorted(self.root.glob("run_*.json")):
                run_id = state_path.stem
                if RUN_ID_PATTERN.fullmatch(run_id) is None or state_path.is_symlink():
                    continue
                try:
                    state = RunState.model_validate_json(state_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    # Never guess whether an unreadable or malformed state is expired.
                    continue
                if (
                    state.run_id != run_id
                    or state.status in {RunStatus.PENDING, RunStatus.RUNNING}
                    or state.updated_at >= cutoff
                ):
                    continue
                self._delete_locked(run_id, state_path)
                deleted.append(run_id)
        return deleted

    def _delete_locked(self, run_id: str, state_path: Path) -> None:
        run_path = self.run_root / run_id
        if run_path.is_symlink():
            run_path.unlink()
        elif run_path.exists():
            shutil.rmtree(run_path)
        state_path.unlink()
        state_path.with_suffix(".json.tmp").unlink(missing_ok=True)
