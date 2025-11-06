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

__all__ = [
    'TaskContextError',
    'TaskBatch',
    'load_task_batch',
    'build_task_prompt',
    'load_task_prompt',
]


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
        if not text:
            continue
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
            continue
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

    ready_specs = batch.ready[:ready_limit]
    blocked_specs = batch.blocked[:blocked_limit]

    sections: list[str] = []

    sections.append('## Ready Tasks')
    if ready_specs:
        ready_summary = summarise_tasks_for_prompt(
            ready_specs,
            limit=len(ready_specs),
        )
        sections.append(ready_summary)
    else:
        sections.append('No ready tasks.')

    sections.append('')
    sections.append('## Blocked Tasks')
    if blocked_specs:
        blocked_lines: list[str] = []
        for spec in blocked_specs:
            priority_label = spec.priority or 'unspecified'
            blocked_lines.append(f'- [{priority_label}] {spec.task_id}: {spec.summary}')
            missing = batch.missing_dependencies(spec)
            if missing:
                blocked_lines.append(f'  * Blocked by: {", ".join(missing)}')
            else:
                blocked_lines.append('  * Blocked by: satisfied dependencies (await manual review).')
            if spec.has_acceptance_criteria():
                for criterion in spec.acceptance_criteria:
                    blocked_lines.append(f'  * {criterion}')
            else:
                blocked_lines.append('  * No acceptance criteria recorded.')
        sections.append('\n'.join(blocked_lines))
    else:
        sections.append('No blocked tasks.')

    if batch.completed:
        sections.append('')
        sections.append('## Completed Tasks')
        for task_id in batch.completed:
            sections.append(f'- {task_id}')

    return '\n'.join(sections).strip()


def load_task_prompt(
    tasks_dir: Path | str | None = None,
    *,
    completed: Iterable[str] | None = None,
    ready_limit: int = 3,
    blocked_limit: int = 3,
) -> tuple[TaskBatch, str]:
    '''Return both the loaded task batch and a formatted prompt summary.'''
    batch = load_task_batch(tasks_dir, completed=completed)
    prompt = build_task_prompt(batch, ready_limit=ready_limit, blocked_limit=blocked_limit)
    return batch, prompt
