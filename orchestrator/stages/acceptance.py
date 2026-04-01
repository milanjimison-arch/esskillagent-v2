"""AcceptanceStage — stub for TDD RED phase.

Do NOT implement logic here yet; tests must fail first.
"""
from __future__ import annotations

from typing import Any

from orchestrator.stages.base import Stage


class AcceptanceStage(Stage):
    """Acceptance stage: runs acceptor agent, generates traceability matrix,
    and performs the final review gate.
    """

    async def _execute_steps(self) -> dict[str, Any]:
        raise NotImplementedError("not implemented")
