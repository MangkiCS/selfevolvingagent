"""Utilities for loading task specifications from disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from agent.core.taskspec import TaskSpec

SUPPORTED_EXTENSIONS: tuple[str, ...] = (".json",)


class TaskSpecLoadingError(RuntimeError):
    """Raised when task specification files cannot be parsed."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")


def load_task_specs(directory: Path | str) -> list[TaskSpec]:
    """Load all task specifications from *directory*.

    Task files must use one of the supported extensions (currently only ``.json``)
    and may contain either a single task object, an array of task objects, or an
    object with a top-level ``tasks`` array. Hidden files and directories are
    ignored.

    Args:
        directory: Directory to scan for task specification files.

    Returns:
        A list of :class:`TaskSpec` instances sorted by file path and declaration order.

    Raises:
        FileNotFoundError: If *directory* does not exist.
        NotADirectoryError: If *directory* is not a directory.
        TaskSpecLoadingError: If a task file cannot be parsed or validated.
    """
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(f"Task specification directory {root} does not exist.")
    if not root.is_dir():
        raise NotADirectoryError(f"Task specification path {root} is not a directory.")

    task_specs: list[TaskSpec] = []
    seen_task_ids: dict[str, Path] = {}

    for file_path in _discover_task_files(root):
        for spec in _load_task_specs_from_file(file_path):
            duplicate_path = seen_task_ids.get(spec.task_id)
            if duplicate_path is not None:
                raise TaskSpecLoadingError(
                    file_path,
                    f"Duplicate task_id {spec.task_id!r}; already defined in {duplicate_path}.",
                )
            seen_task_ids[spec.task_id] = file_path
            task_specs.append(spec)

    return task_specs


def _discover_task_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if _is_hidden(path, root):
            continue
        files.append(path)
    files.sort()
    return files


def _is_hidden(path: Path, root: Path) -> bool:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        # ``path`` is not inside ``root``.
        return False
    return any(part.startswith(".") for part in relative_parts)


def _load_task_specs_from_file(path: Path) -> list[TaskSpec]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TaskSpecLoadingError(path, f"Invalid JSON payload: {exc}") from exc

    entries = _coerce_task_entries(raw, path)

    specs: list[TaskSpec] = []
    for index, data in enumerate(entries):
        try:
            specs.append(TaskSpec.from_dict(data))
        except Exception as exc:  # noqa: BLE001
            raise TaskSpecLoadingError(path, f"Task entry #{index} is invalid: {exc}") from exc

    return specs


def _coerce_task_entries(raw: object, path: Path) -> Sequence[dict[str, object]]:
    if isinstance(raw, dict):
        if "tasks" in raw:
            tasks = raw["tasks"]
            if not isinstance(tasks, list):
                raise TaskSpecLoadingError(path, "'tasks' must be a list of task definitions.")
            entries = tasks
        else:
            entries = [raw]
    elif isinstance(raw, list):
        entries = raw
    else:
        raise TaskSpecLoadingError(
            path,
            "Task file must contain a JSON object, an array of tasks, or an object with a 'tasks' array.",
        )

    validated: list[dict[str, object]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise TaskSpecLoadingError(path, f"Task entry #{index} is not a JSON object.")
        validated.append(entry)

    return validated


__all__ = ["TaskSpecLoadingError", "load_task_specs"]
