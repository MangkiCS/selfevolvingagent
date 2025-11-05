'''Persistence helpers for tracking completed tasks across orchestrator runs.'''
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_PATH = ROOT / 'state' / 'task_state.json'

__all__ = ['CompletedTaskStore', 'TaskStateError', 'load_completed_tasks']


class TaskStateError(RuntimeError):
    '''Raised when task state files cannot be parsed or validated.'''

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f'{path}: {message}')


class CompletedTaskStore:
    '''Manage persistence of completed TaskSpec identifiers across runs.'''

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_STATE_PATH
        self._completed: set[str] = set()
        self.reload()

    def reload(self) -> tuple[str, ...]:
        '''Reload task identifiers from disk, returning the current state.'''
        self._completed = _read_completed(self.path)
        return self.completed

    @property
    def completed(self) -> tuple[str, ...]:
        '''Return the completed task identifiers in sorted order.'''
        return tuple(sorted(self._completed))

    def is_completed(self, task_id: object) -> bool:
        '''Return ``True`` when *task_id* is marked as completed.'''
        try:
            normalised = _normalise_task_id(task_id)
        except ValueError:
            return False
        return normalised in self._completed

    def __contains__(self, task_id: object) -> bool:  # pragma: no cover - delegated
        return self.is_completed(task_id)

    def __iter__(self) -> Iterator[str]:
        '''Iterate over completed task identifiers in sorted order.'''
        yield from self.completed

    def mark_completed(self, task_id: object) -> None:
        '''Record *task_id* as completed and persist the updated state.'''
        normalised = _normalise_task_id(task_id)
        if normalised in self._completed:
            return
        self._completed.add(normalised)
        self._persist()

    def mark_incomplete(self, task_id: object) -> None:
        '''Remove *task_id* from the completed set, persisting the result.'''
        normalised = _normalise_task_id(task_id)
        if normalised not in self._completed:
            return
        self._completed.remove(normalised)
        self._persist()

    def clear(self) -> None:
        '''Clear all completed task identifiers and persist an empty state.'''
        if not self._completed and not self.path.exists():
            return
        self._completed.clear()
        self._persist()

    def _persist(self) -> None:
        _write_completed(self.path, self._completed)


def load_completed_tasks(path: Path | str | None = None) -> tuple[str, ...]:
    '''Return the completed task identifiers stored at *path*.'''
    state_path = Path(path) if path is not None else DEFAULT_STATE_PATH
    return tuple(sorted(_read_completed(state_path)))


def _read_completed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:  # pragma: no cover - exercised via tests
        raise TaskStateError(path, f'Invalid JSON payload: {exc}') from exc

    if raw is None:
        return set()
    if isinstance(raw, dict):
        entries = raw.get('completed', [])
    elif isinstance(raw, list):
        entries = raw
    else:
        raise TaskStateError(
            path,
            "Task state must be stored as a list or an object with a 'completed' field.",
        )

    if not isinstance(entries, list):
        raise TaskStateError(path, "'completed' must be a list of task identifiers.")

    completed: set[str] = set()
    for index, entry in enumerate(entries):
        try:
            task_id = _normalise_task_id(entry)
        except ValueError as exc:
            raise TaskStateError(path, f'Entry #{index} is invalid: {exc}') from exc
        completed.add(task_id)

    return completed


def _write_completed(path: Path, completed: Iterable[str]) -> None:
    normalised = {_normalise_task_id(task_id) for task_id in completed}
    payload = {'completed': sorted(normalised)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _normalise_task_id(task_id: object) -> str:
    if task_id is None:
        raise ValueError('task identifier must not be None.')
    text = str(task_id).strip()
    if not text:
        raise ValueError('task identifier must not be blank.')
    return text
