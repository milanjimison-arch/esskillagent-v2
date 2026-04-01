"""Review pipeline stub.

Three-way parallel review pipeline (code, security, brooks),
auto-fix loop on failure, and feature-gap detection with supplemental
task creation.

This is a minimal stub so that tests can import the module without
ImportError. All public callables raise NotImplementedError until
the GREEN phase implements them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data-transfer objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewerResult:
    """Result returned by a single reviewer."""

    reviewer: str
    passed: bool
    issues: tuple[str, ...]
    verdict: str


@dataclass(frozen=True)
class PipelineReviewResult:
    """Aggregated result from all three parallel reviewers."""

    passed: bool
    reviewer_results: dict[str, ReviewerResult]
    attempts: int
    gaps: list[str]
    supplemental_tasks: list[str]


@dataclass(frozen=True)
class FeatureGap:
    """A single detected gap between spec and implementation."""

    description: str
    supplemental_task: str


# ---------------------------------------------------------------------------
# Reviewer callables (stubs)
# ---------------------------------------------------------------------------


async def run_code_reviewer(context: dict[str, Any]) -> ReviewerResult:
    """Run the code quality reviewer."""
    raise NotImplementedError("run_code_reviewer not implemented")


async def run_security_reviewer(context: dict[str, Any]) -> ReviewerResult:
    """Run the security reviewer."""
    raise NotImplementedError("run_security_reviewer not implemented")


async def run_brooks_reviewer(context: dict[str, Any]) -> ReviewerResult:
    """Run the Brooks (architectural/design) reviewer."""
    raise NotImplementedError("run_brooks_reviewer not implemented")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class ReviewPipeline:
    """Three-way parallel review pipeline with auto-fix loop and gap detection."""

    DEFAULT_MAX_RETRIES: int = 3

    def __init__(self, *, max_retries: int = DEFAULT_MAX_RETRIES) -> None:
        self.max_retries = max_retries

    async def run(self, context: dict[str, Any]) -> PipelineReviewResult:
        """Execute the full review pipeline."""
        raise NotImplementedError("ReviewPipeline.run not implemented")

    async def run_parallel_reviews(
        self, context: dict[str, Any]
    ) -> dict[str, ReviewerResult]:
        """Run all three reviewers concurrently and return their results."""
        raise NotImplementedError("ReviewPipeline.run_parallel_reviews not implemented")

    async def auto_fix_loop(
        self,
        context: dict[str, Any],
        failed_results: dict[str, ReviewerResult],
    ) -> dict[str, ReviewerResult]:
        """Trigger fixer and re-run failed reviewers until pass or retry limit."""
        raise NotImplementedError("ReviewPipeline.auto_fix_loop not implemented")

    async def detect_feature_gaps(
        self, context: dict[str, Any]
    ) -> list[FeatureGap]:
        """Detect gaps between spec and implementation."""
        raise NotImplementedError("ReviewPipeline.detect_feature_gaps not implemented")

    async def create_supplemental_tasks(
        self, gaps: list[FeatureGap]
    ) -> list[str]:
        """Create supplemental tasks for each detected feature gap."""
        raise NotImplementedError(
            "ReviewPipeline.create_supplemental_tasks not implemented"
        )
