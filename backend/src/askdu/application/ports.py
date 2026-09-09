from __future__ import annotations

from typing import Protocol

from askdu.domain import AnalyticalContract, RunState


class RunRepository(Protocol):
    def save(self, state: RunState) -> None: ...

    def get(self, run_id: str) -> RunState | None: ...


class ChatModel(Protocol):
    """Server-side text model boundary; implementations must not expose credentials."""

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2_000,
        temperature: float = 0.0,
    ) -> str: ...


class QuestionCompilerPort(Protocol):
    """Question-to-contract boundary shared by registry and model compilers."""

    def compile(self, question: str) -> AnalyticalContract: ...
