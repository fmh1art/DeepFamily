from __future__ import annotations

import re

from askdu.domain import RunState

PUBLIC_RUN_FAILURE = "Execution failed; the detailed cause is retained server-side."
PUBLIC_PROVIDER_FAILURE = (
    "External model planning failed. Check provider availability, quota, and the pinned "
    "gateway profile, then retry."
)


def public_run_state(state: RunState) -> RunState:
    """Return a browser-safe copy while preserving actionable provider status."""

    if state.error is None:
        return state
    provider_status = re.fullmatch(
        r"ChatModelError: Provider request failed with HTTP ([1-5][0-9]{2})",
        state.error,
    )
    if provider_status is not None:
        return state.model_copy(
            update={
                "error": (
                    "External model planning was rejected by the provider "
                    f"(HTTP {provider_status.group(1)}). Check the pinned gateway profile "
                    "or quota, then retry."
                )
            }
        )
    if state.error.startswith("ChatModelError:"):
        return state.model_copy(update={"error": PUBLIC_PROVIDER_FAILURE})
    return state.model_copy(update={"error": PUBLIC_RUN_FAILURE})
