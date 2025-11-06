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


def _format_blocked_section(batch: TaskBatch, blocked_limit: int) -> str:
    blocked_specs = batch.blocked[:blocked_limit]
    if not blocked_specs:
        return 'No blocked tasks.'
    lines: list[str] = []
    for spec in blocked_specs:
        priority_label = spec.priority or 'unspecified'
        lines.append(f"- [{priority_label}] {spec.task_id}: {spec.summary}")
        missing = batch.missing_dependencies(spec)
        if missing:
            lines.append(f"  * Blocked by: {', '.join(missing)}")
        else:
            lines.append('  * Blocked by: dependencies satisfied; awaiting scheduling.')
        if spec.has_acceptance_criteria():
            for criterion in spec.acceptance_criteria:
                lines.append(f"  * Acceptance: {criterion}")
    return '\n'.join(lines)


def build_task_prompt(
    batch: TaskBatch,
    *,
    ready_limit: int = 3,
    blocked_limit: int = 3,
) -> str:
    '''Render a markdown summary of ready and blocked tasks for prompt inclusion.'''
    if ready_limit <= 0:
        raise ValueError('ready_limit must be positive.')
    if blocked_limit <= 0:
        raise ValueError('blocked_limit must be positive.')

    sections: list[str] = ['## Ready Tasks']

    if batch.ready:
        sections.append(summarise_tasks_for_prompt(batch.ready, limit=ready_limit))
    else:
        sections.append('No pending tasks.')

    sections.append('## Blocked Tasks')
    sections.append(_format_blocked_section(batch, blocked_limit))

    if batch.completed:
        sections.append('## Completed Task References')
        sections.append(', '.join(batch.completed))

    return '\n\n'.join(sections)


def load_task_prompt(
    tasks_dir: Path | str | None = None,
    *,
    completed: Iterable[str] | None = None,
    ready_limit: int = 3,
    blocked_limit: int = 3,
) -> TaskPrompt:
    '''Load task specifications and return a structured prompt payload for orchestration.'''
    batch = load_task_batch(tasks_dir, completed=completed)
    prompt = build_task_prompt(batch, ready_limit=ready_limit, blocked_limit=blocked_limit)
    return TaskPrompt(batch=batch, prompt=prompt)
