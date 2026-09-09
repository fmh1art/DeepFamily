from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

from askdu.adapters.catalog import FileCatalog
from askdu.application.orchestrator import RunService
from askdu.domain import RunState, RunStatus
from deployment.repository import ManagedFileRunRepository


class ActiveRunDeletionError(RuntimeError):
    """Raised when deletion is requested before a run reaches a terminal state."""


class DeploymentRunService:
    """Apply public lifecycle policy while delegating analysis to the frozen core."""

    def __init__(
        self,
        core: RunService,
        repository: ManagedFileRunRepository,
        run_retention_hours: int,
    ) -> None:
        if not 0 <= run_retention_hours <= 720:
            raise ValueError("run_retention_hours must be between 0 and 720")
        if core.repository is not repository:
            raise ValueError("The deployment service and analytical core must share a repository")
        self._core = core
        self._repository = repository
        self.run_retention_hours = run_retention_hours
        self._retention_lock = threading.Lock()
        self._last_retention_sweep: float | None = None

    @property
    def environment_id(self) -> str:
        return self._core.environment_id

    @property
    def catalog(self) -> FileCatalog:
        return self._core.catalog

    @property
    def planner_mode(self) -> Literal["registry", "model", "agentic"]:
        return self._core.planner_mode

    def run(self, question: str) -> RunState:
        self.prune_expired_runs()
        return self._core.run(question)

    def submit(self, question: str) -> RunState:
        self.prune_expired_runs()
        return self._core.submit(question)

    def get(self, run_id: str) -> RunState | None:
        return self._core.get(run_id)

    def delete(self, run_id: str) -> bool:
        state = self._repository.get(run_id)
        if state is None:
            return False
        if state.status in {RunStatus.PENDING, RunStatus.RUNNING}:
            raise ActiveRunDeletionError("Run is still active")
        return self._repository.delete(run_id)

    def prune_expired_runs(self, *, force: bool = False) -> list[str]:
        """Throttle expiry work while allowing readiness to enforce retention."""

        if self.run_retention_hours == 0:
            return []
        with self._retention_lock:
            monotonic_now = time.monotonic()
            if (
                not force
                and self._last_retention_sweep is not None
                and monotonic_now - self._last_retention_sweep < 60.0
            ):
                return []
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.run_retention_hours)
            deleted = self._repository.prune_before(cutoff)
            self._last_retention_sweep = monotonic_now
            return deleted
