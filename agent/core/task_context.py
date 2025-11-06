'''Utilities for collating TaskSpec data into orchestrator-ready context.'''
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from agent.core.task_loader import TaskSpecLoadingError, load_task_specs
from agent.core.task_selection import order_by_priority, summarise_tasks_for_prompt
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
        TaskContextError: When the directory cannot be read or contains invalid
            specifications.
    '''
    tasks_path = Path(tasks_dir) if tasks_dir is not None else DEFAULT_TASKS_DIR
    completed_ids = _normalise_completed(completed)
    completed_set = set(completed_ids)

    try:
        specs = load_task_specs(tasks_path)
    except (FileNotFoundError, NotADirectoryError) as exc:  # pragma: no cover - exercised via tests
        raise TaskContextError(tasks_path, str(exc)) from exc
    except TaskSpecLoadingError as exc:
        raise TaskContextError(tasks_path, str(exc)) from exc

    ordered_specs = order_by_priority(specs)
    ready: list[TaskSpec] = []
    blocked: list[TaskSpec] = []

    for spec in ordered_specs:
        if all(dependency in completed_set for dependency in spec.dependencies):
            ready.append(spec)
        else:
            blocked.append(spec)

    return TaskBatch(tuple(ready), tuple(blocked), completed_ids)


def build_task_prompt(
    batch: TaskBatch,
    *,
    ready_limit: int = 3,
    blocked_limit: int = 3,
) -> str:
    '''Return a Markdown-formatted summary of ready, blocked, and completed tasks.'''
    if ready_limit <= 0:
        raise ValueError('ready_limit must be positive.')
    if blocked_limit <= 0:
        raise ValueError('blocked_limit must be positive.')

    sections: list[str] = []
    sections.append(_render_ready_section(batch, ready_limit))
    sections.append(_render_blocked_section(batch, blocked_limit))

    completed_section = _render_completed_section(batch)
    if completed_section is not None:
        sections.append(completed_section)

    return '\n\n'.join(section for section in sections if section).strip()


def load_task_prompt(
    tasks_dir: Path | str | None = None,
    *,
    ready_limit: int = 3,
    blocked_limit: int = 3,
    completed: Iterable[str] | None = None,
) -> TaskPrompt:
    '''Load task specifications and return both structured and rendered context.'''
    if ready_limit <= 0:
        raise ValueError('ready_limit must be positive.')
    if blocked_limit <= 0:
        raise ValueError('blocked_limit must be positive.')

    batch = load_task_batch(tasks_dir, completed=completed)
    prompt = build_task_prompt(batch, ready_limit=ready_limit, blocked_limit=blocked_limit)
    return TaskPrompt(batch=batch, prompt=prompt)


def _render_ready_section(batch: TaskBatch, limit: int) -> str:
    lines = ['## Ready Tasks']
    if not batch.ready:
        lines.append('No ready tasks.')
        return '\n'.join(lines)

    visible = min(limit, len(batch.ready))
    lines.append(summarise_tasks_for_prompt(batch.ready, limit=visible))
    hidden = len(batch.ready) - visible
    if hidden > 0:
        lines.append(f'... {hidden} more ready task(s) not shown.')
    return '\n'.join(lines)


def _render_blocked_section(batch: TaskBatch, limit: int) -> str:
    lines = ['## Blocked Tasks']
    if not batch.blocked:
        lines.append('No blocked tasks.')
        return '\n'.join(lines)

    for spec in batch.blocked[:limit]:
        priority_label = spec.priority or 'unspecified'
        lines.append(f'- [{priority_label}] {spec.task_id}: {spec.summary}')
        missing = batch.missing_dependencies(spec)
        if missing:
            lines.append(f'  * Blocked by: {", ".join(missing)}')
        else:
            lines.append('  * Blocked by: (no recorded dependencies)')
    hidden = len(batch.blocked) - min(limit, len(batch.blocked))
    if hidden > 0:
        lines.append(f'... {hidden} more blocked task(s) not shown.')
    return '\n'.join(lines)


def _render_completed_section(batch: TaskBatch) -> str | None:
    if not batch.completed:
        return None
    lines = ['## Completed Tasks']
    for task_id in batch.completed:
        lines.append(f'- {task_id}')
    return '\n'.join(lines)
