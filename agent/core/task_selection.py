"""Task selection utilities for orchestrator pipeline.

This module centralises logic for prioritising and formatting TaskSpec entries
so the orchestrator can reason about backlog items without duplicating sorting
rules.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from typing import Final

from agent.core.taskspec import TaskPriority, TaskSpec

__all__ = ["order_by_priority", "select_next_task", "summarise_tasks_for_prompt"]

_PRIORITY_ORDER: Final[dict[TaskPriority, int]] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


def _priority_rank(priority: TaskPriority | None) -> int:
    """Return a sortable rank for the provided priority value."""
    if priority is None:
        return len(_PRIORITY_ORDER)
    return _PRIORITY_ORDER[priority]


def order_by_priority(specs: Iterable[TaskSpec]) -> list[TaskSpec]:
    """Return *specs* ordered by priority while preserving stable ordering within tiers."""
    specs_list = list(specs)
    ranked = sorted(
        enumerate(specs_list),
        key=lambda item: (_priority_rank(item[1].priority), item[0]),
    )
    return [spec for _, spec in ranked]


def select_next_task(
    specs: Sequence[TaskSpec],
    *,
    completed: Collection[str] | None = None,
) -> TaskSpec | None:
    """Return the highest-priority task with all dependencies satisfied.

    Args:
        specs: Candidate task specifications.
        completed: Optional collection of task identifiers that have already been
            completed. Tasks whose dependencies are not all present in this
            collection are skipped.

    Returns:
        The next task to execute, or ``None`` when no tasks are eligible.
    """
    completed_ids = set(completed or ())
    for spec in order_by_priority(specs):
        if any(dependency not in completed_ids for dependency in spec.dependencies):
            continue
        return spec
    return None


def summarise_tasks_for_prompt(
    specs: Sequence[TaskSpec],
    *,
    limit: int = 3,
) -> str:
    """Render a human-readable summary of the highest-priority tasks.

    Args:
        specs: Candidate task specifications to summarise.
        limit: Maximum number of tasks to include in the summary; must be
            positive.

    Returns:
        A multi-line bullet list describing up to ``limit`` tasks. When no tasks
        are provided, ``"No pending tasks."`` is returned.
    """
    if limit <= 0:
        raise ValueError("limit must be positive.")

    selected = order_by_priority(specs)[:limit]
    if not selected:
        return "No pending tasks."

    lines: list[str] = []
    for spec in selected:
        priority_label = spec.priority or "unspecified"
        lines.append(f"- [{priority_label}] {spec.task_id}: {spec.summary}")
        if spec.has_acceptance_criteria():
            for criterion in spec.acceptance_criteria:
                lines.append(f"  * {criterion}")
        else:
            lines.append("  * No acceptance criteria recorded.")
        if spec.dependencies:
            deps = ", ".join(spec.dependencies)
            lines.append(f"  * Dependencies: {deps}")
    return "\n".join(lines)
