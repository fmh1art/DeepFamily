from __future__ import annotations

import re
import threading
from pathlib import Path

from askdu.domain import RunState

RUN_ID_PATTERN = re.compile(r"^run_[a-f0-9]{16}$")


class FileRunRepository:
    """Small, atomic persistence adapter for the initial single-node service."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def save(self, state: RunState) -> None:
        path = self._path_for(state.run_id)
        temporary = path.with_suffix(".json.tmp")
        payload = state.model_dump_json(indent=2)
        with self._lock:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(path)

    def get(self, run_id: str) -> RunState | None:
        path = self._path_for(run_id)
        if not path.exists():
            return None
        with self._lock:
            return RunState.model_validate_json(path.read_text(encoding="utf-8"))

    def _path_for(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError("Invalid run identifier")
        return self.root / f"{run_id}.json"
