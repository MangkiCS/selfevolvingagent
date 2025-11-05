'''Utilities for collating TaskSpec data into orchestrator-ready context.'''
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agent.core.task_loader import TaskSpecLoadingError, load_task_specs
from agent.core.task_selection import order_by_priority, summarise_tasks_for_prompt
from agent.core.taskspec import TaskSpec

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_DIR = ROOT / 'tasks'

__all__ = ['TaskContextError', 'TaskBatch', 'load_task_batch', 'build_task_prompt']


class TaskContextError(RuntimeError):
    '''Raised when task specifications cannot be loaded for orchestration.'''

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f'{path}: {message}')


@dataclass(frozen=True, slots=True)
class TaskBatch:
    '''Partitioned view of task specifications for orchestrator runs.'''

    ready: tuple[TaskSpec, ...]
    blocked: tuple[TaskSpec, ...]
    completed: tuple[str, ...]

    def is_empty(self) -> bool:
        '''Return True when no ready or blocked tasks are present.'''
        return not self.ready and not self.blocked

    def missing_dependencies(self, spec: TaskSpec) -> tuple[str, ...]:
        '''Return dependencies of *spec* that are not marked as completed.'''
        completed_set = set(self.completed)
        return tuple(dep for dep in spec.dependencies if dep not in completed_set)


def _normalise_completed(completed: Iterable[str] | None) -> tuple[str, ...]:
    '''Return a sorted tuple of normalised completed task identifiers.'''
    if completed is None:
        return ()
    normalised: set[str] = set()
    for entry in completed:
        if entry is None:
            continue
        text = str(entry).strip()
        if text:
            normalised.add(text)
    return tuple(sorted(normalised))


def load_task_batch(
    tasks_dir: Path | str | None = None,
    *,
    completed: Iterable[str] | None = None,
) -> TaskBatch:
    '''Load task specifications and partition them into ready and blocked sets.

    Args:
        tasks_dir: Directory containing task specification files. Defaults to
            the repository ``tasks/`` directory when not provided.
        completed: Iterable of task identifiers already completed in previous
            runs.

    Returns:
        A :class:`TaskBatch` containing tasks whose dependencies are satisfied
        (ready) and those still blocked by unmet dependencies.

    Raises:
        TaskContextError: When the directory cannot be read or a task file is
            invalid.
    '''
    directory = Path(tasks_dir) if tasks_dir is not None else DEFAULT_TASKS_DIR
    completed_ids = _normalise_completed(completed)
    completed_set = set(completed_ids)

    try:
        specs = load_task_specs(directory)
    except FileNotFoundError as exc:
        raise TaskContextError(directory, 'Task specification directory not found.') from exc
    except NotADirectoryError as exc:
        raise TaskContextError(directory, 'Task specification path is not a directory.') from exc
    except TaskSpecLoadingError as exc:
        details = str(exc)
        prefix = f'{exc.path}: '
        if details.startswith(prefix):
            details = details[len(prefix):]
        raise TaskContextError(exc.path, f'Invalid task specification: {details}') from exc

    ready: list[TaskSpec] = []
    blocked: list[TaskSpec] = []
    for spec in order_by_priority(specs):
        if spec.dependencies and not all(dep in completed_set for dep in spec.dependencies):
            blocked.append(spec)
        else:
            ready.append(spec)

    return TaskBatch(
        ready=tuple(ready),
        blocked=tuple(blocked),
        completed=completed_ids,
    )


def build_task_prompt(
    batch: TaskBatch,
    *,
    ready_limit: int = 3,
    blocked_limit: int = 3,
) -> str:
    '''Render a prompt-ready task summary for the orchestrator.'''
    if ready_limit <= 0:
        raise ValueError('ready_limit must be positive.')
    if blocked_limit <= 0:
        raise ValueError('blocked_limit must be positive.')

    lines: list[str] = []

    lines.append('## Ready Tasks')
    if batch.ready:
        visible_ready = min(ready_limit, len(batch.ready))
        ready_summary = summarise_tasks_for_prompt(batch.ready, limit=visible_ready)
        lines.append(ready_summary)
        remaining_ready = len(batch.ready) - visible_ready
        if remaining_ready > 0:
            lines.append(f'... {remaining_ready} additional ready task(s) not shown.')
    else:
        lines.append('No ready tasks.')

    lines.append('')
    lines.append('## Blocked Tasks')
    if batch.blocked:
        completed_set = set(batch.completed)
        visible_blocked = order_by_priority(batch.blocked)[:blocked_limit]
        for spec in visible_blocked:
            priority_label = spec.priority or 'unspecified'
            lines.append(f'- [{priority_label}] {spec.task_id}: {spec.summary}')
            missing = [dep for dep in spec.dependencies if dep not in completed_set]
            if missing:
                missing_labels = ', '.join(missing)
                lines.append(f'  * Blocked by: {missing_labels}')
            else:
                lines.append('  * Blocked by: Unknown dependencies.')
            if spec.has_acceptance_criteria():
                for criterion in spec.acceptance_criteria:
                    lines.append(f'  * {criterion}')
        remaining_blocked = len(batch.blocked) - len(visible_blocked)
        if remaining_blocked > 0:
            lines.append(f'  * ... {remaining_blocked} additional blocked task(s) not shown.')
    else:
        lines.append('No blocked tasks.')

    return '\\n'.join(lines)
