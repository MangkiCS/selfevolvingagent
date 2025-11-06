'''Utilities for collating TaskSpec data into orchestrator-ready context.'''
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from agent.core.task_loader import TaskSpecLoadingError, load_task_specs
from agent.core.task_selection import order_by_priority, summarise_tasks_for_prompt
from agent.core.task_state import DEFAULT_STATE_PATH, TaskStateError, load_completed_tasks
from agent.core.taskspec import TaskSpec

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_DIR = ROOT / 'tasks'

__all__ = [
    'TaskContextError',
    'TaskBatch',
    'TaskPrompt',
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


@dataclass(frozen=True, slots=True)
class TaskPrompt:
    '''Structured payload combining a task batch with a formatted prompt section.'''

    batch: TaskBatch
    prompt: str

    def is_empty(self) -> bool:
        '''Return True when no ready or blocked tasks are described.'''
        return self.batch.is_empty()

    def has_ready_tasks(self) -> bool:
        '''Return True when at least one task is ready for execution.'''
        return bool(self.batch.ready)

    @property
    def ready(self) -> tuple[TaskSpec, ...]:
        '''Expose the ready task specifications.'''
        return self.batch.ready

    @property
    def blocked(self) -> tuple[TaskSpec, ...]:
        '''Expose the blocked task specifications.'''
        return self.batch.blocked

    @property
    def completed(self) -> tuple[str, ...]:
        '''Expose the normalised completed task identifiers.'''
        return self.batch.completed

    def to_dict(self) -> dict[str, Any]:
        '''Return a serialisable representation suitable for logging or prompts.'''
        return {
            'prompt': self.prompt,
            'ready_task_ids': [spec.task_id for spec in self.batch.ready],
            'blocked_task_ids': [spec.task_id for spec in self.batch.blocked],
            'completed_task_ids': list(self.batch.completed),
        }


def load_task_batch(
    tasks_dir: Path | str | None = None,
    *,
    completed: Iterable[str] | None = None,
    state_path: Path | str | None = None,
) -> TaskBatch:
    '''Load task specifications and partition them into ready and blocked sets.

    Args:
        tasks_dir: Directory containing task specification files. Defaults to the
            repository ``tasks/`` directory when not provided.
        completed: Iterable of task identifiers already completed in previous
            runs. When omitted, the persisted task state (see ``state_path``) is
            consulted.
        state_path: Path to a persisted completed-task store. Defaults to the
            repository ``state/task_state.json``.

    Returns:
        A :class:`TaskBatch` containing tasks whose dependencies are satisfied
        (ready) and those still blocked by unmet dependencies.

    Raises:
        TaskContextError: When the task directory or state file cannot be read.
    '''
    tasks_path = _resolve_tasks_dir(tasks_dir)
    completed_ids = _resolve_completed_ids(completed, state_path)

    specs = _load_task_specs(tasks_path)
    ready, blocked = _partition_tasks(specs, completed_ids)

    return TaskBatch(ready=ready, blocked=blocked, completed=completed_ids)


def build_task_prompt(
    batch: TaskBatch,
    *,
    ready_limit: int = 3,
    blocked_limit: int = 3,
) -> str:
    '''Render a human-readable summary of ready and blocked tasks.

    Args:
        batch: Partitioned task specifications.
        ready_limit: Maximum number of ready tasks to include.
        blocked_limit: Maximum number of blocked tasks to include.

    Returns:
        Markdown-formatted prompt text describing the current backlog state.
    '''
    if ready_limit <= 0:
        raise ValueError('ready_limit must be positive.')
    if blocked_limit <= 0:
        raise ValueError('blocked_limit must be positive.')

    sections: list[str] = []

    sections.append('## Ready Tasks')
    ready_section = _render_ready_section(batch.ready, limit=ready_limit)
    if ready_section:
        sections.extend(ready_section)
    else:
        sections.append('No ready tasks detected.')

    blocked_section = _render_blocked_section(batch, limit=blocked_limit)
    if blocked_section:
        sections.append('')
        sections.append('## Blocked Tasks')
        sections.extend(blocked_section)

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
    state_path: Path | str | None = None,
    ready_limit: int = 3,
    blocked_limit: int = 3,
) -> TaskPrompt:
    '''Return a :class:`TaskPrompt` containing task partitions and prompt text.'''
    batch = load_task_batch(
        tasks_dir,
        completed=completed,
        state_path=state_path,
    )
    prompt = build_task_prompt(batch, ready_limit=ready_limit, blocked_limit=blocked_limit)
    return TaskPrompt(batch=batch, prompt=prompt)


def _resolve_tasks_dir(tasks_dir: Path | str | None) -> Path:
    if tasks_dir is None:
        return DEFAULT_TASKS_DIR
    return Path(tasks_dir)


def _resolve_state_path(state_path: Path | str | None) -> Path:
    if state_path is None:
        return DEFAULT_STATE_PATH
    return Path(state_path)


def _resolve_completed_ids(
    completed: Iterable[str] | None,
    state_path: Path | str | None,
) -> tuple[str, ...]:
    if completed is not None:
        return _normalise_completed(completed)

    resolved_state_path = _resolve_state_path(state_path)
    try:
        stored = load_completed_tasks(resolved_state_path)
    except TaskStateError as exc:
        raise TaskContextError(resolved_state_path, f'Failed to load completed task state: {exc}') from exc
    return _normalise_completed(stored)


def _load_task_specs(path: Path) -> Sequence[TaskSpec]:
    try:
        return load_task_specs(path)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise TaskContextError(path, str(exc)) from exc
    except TaskSpecLoadingError as exc:
        raise TaskContextError(exc.path, str(exc)) from exc


def _partition_tasks(
    specs: Sequence[TaskSpec],
    completed: tuple[str, ...],
) -> tuple[tuple[TaskSpec, ...], tuple[TaskSpec, ...]]:
    completed_set = set(completed)
    ready: list[TaskSpec] = []
    blocked: list[TaskSpec] = []

    for spec in order_by_priority(specs):
        if any(dependency not in completed_set for dependency in spec.dependencies):
            blocked.append(spec)
            continue
        ready.append(spec)

    return tuple(ready), tuple(blocked)


def _render_ready_section(specs: Sequence[TaskSpec], *, limit: int) -> list[str]:
    if not specs:
        return []
    summary = summarise_tasks_for_prompt(specs, limit=limit)
    return summary.splitlines()


def _render_blocked_section(batch: TaskBatch, *, limit: int) -> list[str]:
    specs = batch.blocked
    if not specs:
        return []

    lines: list[str] = []
    for spec in order_by_priority(specs)[:limit]:
        priority_label = spec.priority or 'unspecified'
        lines.append(f'- [{priority_label}] {spec.task_id}: {spec.summary}')

        missing = batch.missing_dependencies(spec)
        if missing:
            deps = ', '.join(missing)
            lines.append(f'  * Blocked by: {deps}')
        else:
            lines.append('  * Blocked by: dependencies previously completed.')
        if spec.has_acceptance_criteria():
            for criterion in spec.acceptance_criteria:
                lines.append(f'  * Acceptance: {criterion}')
        else:
            lines.append('  * No acceptance criteria recorded.')

    return lines


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
