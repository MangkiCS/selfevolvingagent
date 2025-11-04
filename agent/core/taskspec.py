"""Data models describing structured automation tasks."""
from __future__ import annotations

from collections.abc import Iterable as IterableABC, Mapping as MappingABC
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional, Tuple, cast

TaskPriority = Literal["low", "medium", "high", "critical"]

_ALLOWED_PRIORITIES: Tuple[TaskPriority, ...] = ("low", "medium", "high", "critical")


def _normalise_required_text(value: Any, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} must not be None.")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


def _normalise_optional_text(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _normalise_sequence(value: Any, field_name: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        candidates = (value,)
    else:
        if isinstance(value, MappingABC):
            raise TypeError(f"{field_name} must be a sequence of strings, not a mapping.")
        if not isinstance(value, IterableABC):
            raise TypeError(f"{field_name} must be a sequence of strings.")
        candidates = value

    result: list[str] = []
    for raw in candidates:
        if raw is None:
            raise ValueError(f"{field_name} cannot contain None entries.")
        text = str(raw).strip()
        if not text:
            raise ValueError(f"{field_name} cannot contain blank entries.")
        result.append(text)
    return tuple(result)


def _normalise_priority(value: Any) -> Optional[TaskPriority]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text not in _ALLOWED_PRIORITIES:
        allowed = ", ".join(_ALLOWED_PRIORITIES)
        raise ValueError(f"priority must be one of {allowed}, got {value!r}.")
    return cast(TaskPriority, text)


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """Structured description of a unit of work for the automation agent."""

    task_id: str
    title: str
    summary: str
    details: Optional[str] = None
    context: Tuple[str, ...] = field(default_factory=tuple)
    acceptance_criteria: Tuple[str, ...] = field(default_factory=tuple)
    priority: Optional[TaskPriority] = None
    tags: Tuple[str, ...] = field(default_factory=tuple)
    dependencies: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _normalise_required_text(self.task_id, "task_id"))
        object.__setattr__(self, "title", _normalise_required_text(self.title, "title"))
        object.__setattr__(self, "summary", _normalise_required_text(self.summary, "summary"))
        object.__setattr__(self, "details", _normalise_optional_text(self.details, "details"))
        object.__setattr__(self, "context", _normalise_sequence(self.context, "context"))
        object.__setattr__(
            self,
            "acceptance_criteria",
            _normalise_sequence(self.acceptance_criteria, "acceptance_criteria"),
        )
        object.__setattr__(self, "tags", _normalise_sequence(self.tags, "tags"))
        object.__setattr__(self, "dependencies", _normalise_sequence(self.dependencies, "dependencies"))
        object.__setattr__(self, "priority", _normalise_priority(self.priority))

    @classmethod
    def from_dict(cls, data: MappingABC[str, Any]) -> "TaskSpec":
        """Create a specification from a JSON-serialisable mapping."""
        if not isinstance(data, MappingABC):
            raise TypeError("TaskSpec.from_dict expects a mapping input.")
        missing = [field for field in ("task_id", "title", "summary") if field not in data]
        if missing:
            fields = ", ".join(missing)
            raise ValueError(f"TaskSpec.from_dict missing required field(s): {fields}.")

        return cls(
            task_id=data["task_id"],
            title=data["title"],
            summary=data["summary"],
            details=data.get("details"),
            context=data.get("context"),
            acceptance_criteria=data.get("acceptance_criteria"),
            priority=data.get("priority"),
            tags=data.get("tags"),
            dependencies=data.get("dependencies"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise this specification into primitive types suitable for JSON."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "summary": self.summary,
            "details": self.details,
            "context": list(self.context),
            "acceptance_criteria": list(self.acceptance_criteria),
            "priority": self.priority,
            "tags": list(self.tags),
            "dependencies": list(self.dependencies),
        }

    def has_acceptance_criteria(self) -> bool:
        """Return True when at least one acceptance criterion is defined."""
        return bool(self.acceptance_criteria)
