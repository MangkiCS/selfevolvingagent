#!/usr/bin/env python3
"""
Orchestrator MVP (secure subprocess):
- erzeugt Feature-Branch auto/YYYYMMDD-HHMMSS
- ruft optional ein Code-Modell (Responses API) auf
- schreibt Patches/Tests oder fällt auf Beispielcode zurück
- committet, pusht, erstellt PR + Label 'auto'
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Dict, Iterable, List, Optional

from openai import OpenAI

from agent.core.event_log import append_event
from agent.core.task_context import (
    DEFAULT_TASKS_DIR,
    TaskContextError,
    TaskPrompt,
    load_task_prompt,
)
from agent.core.task_loader import TaskSpecLoadingError, load_task_specs
from agent.core.taskspec import TaskSpec
from agent.core.task_selection import select_next_task, summarise_tasks_for_prompt

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTO_BRANCH_PREFIX = "auto/"
AUTO_LABEL = "auto"

# Cached catalogue populated during startup for downstream task selection.
_TASK_CATALOG: Dict[str, TaskSpec] = {}

# Snapshot-Parameter (sparsam halten -> Kosten & Tokens)
SNAPSHOT_MAX_FILES = 40
SNAPSHOT_MAX_BYTES_PER_FILE = 4000
SNAPSHOT_INCLUDE_PREFIXES = ("agent/", "tests/", "docs/")
SNAPSHOT_EXCLUDE_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".pdf", ".mp4", ".zip", ".gz", ".tar", ".7z",
    ".min.js", ".min.css", ".lock", ".exe", ".dll",
)


# ---------------- Shell helper (ohne shell=True) ----------------
def sh(args: List[str], check: bool = True, cwd: pathlib.Path = ROOT) -> str:
    print(f"$ {' '.join(args)}")
    res = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)
    if res.returncode != 0:
        level = "error" if check else "warning"
        stdout = res.stdout[-1000:] if res.stdout else ""
        stderr = res.stderr[-1000:] if res.stderr else ""
        append_event(
            level=level,
            source="subprocess",
            message=f"Command failed: {' '.join(args)}",
            details={
                "returncode": res.returncode,
                "stdout": stdout,
                "stderr": stderr,
            },
        )
        if check:
            raise RuntimeError(f"Command failed: {' '.join(args)}")
    return res.stdout.strip()


def write(path: str, content: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# ---------------- Git helpers ----------------
def ensure_git_identity() -> None:
    # setzt Defaults, überschreibt nur wenn leer
    sh(["git", "config", "user.email", "actions@github.com"], check=False)
    sh(["git", "config", "user.name", "github-actions[bot]"], check=False)


def create_branch() -> str:
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    branch = f"{AUTO_BRANCH_PREFIX}{ts}"
    sh(["git", "checkout", "-b", branch])
    return branch


def commit_all(msg: str) -> None:
    sh(["git", "add", "-A"], check=False)
    status = sh(["git", "status", "--porcelain"], check=False).strip()
    if not status:
        # Nichts zu committen -> erzeugen wir eine kleine Buildmarke
        ts = datetime.datetime.utcnow().isoformat()
        autopath = ROOT / "docs" / "AUTOCOMMIT.md"
        prev = autopath.read_text(encoding="utf-8") if autopath.exists() else "# Auto log\n"
        write("docs/AUTOCOMMIT.md", prev + f"- auto: {ts}\n")
        sh(["git", "add", "docs/AUTOCOMMIT.md"])
    sh(["git", "commit", "-m", msg])


def push_branch(branch: str) -> None:
    sh(["git", "push", "-u", "origin", branch])


# ---------------- Repo-Snapshot ----------------
def build_repo_snapshot(
    max_files: int = SNAPSHOT_MAX_FILES,
    max_bytes_per_file: int = SNAPSHOT_MAX_BYTES_PER_FILE,
) -> str:
    """Baut einen kompakten Markdown-Snapshot des Repos (nur relevante Dateien, gekürzt)."""
    try:
        out = sh(["git", "ls-files"], check=False)
        files = [f for f in out.splitlines() if f]
    except Exception:
        files = []

    # filtern: nur interessante Pfade & keine Binär-/Großdateien
    selected: List[str] = []
    for f in files:
        if not f.startswith(SNAPSHOT_INCLUDE_PREFIXES):
            continue
        if any(f.endswith(ext) for ext in SNAPSHOT_EXCLUDE_SUFFIXES):
            continue
        selected.append(f)
        if len(selected) >= max_files:
            break

    parts: List[str] = []
    for p in selected:
        try:
            data = (ROOT / p).read_text(encoding="utf-8", errors="ignore")[:max_bytes_per_file]
            parts.append(f"### {p}\n```text\n{data}\n```\n")
        except Exception:
            # Datei nicht lesbar -> überspringen
            continue

    header = f"_Snapshot: {len(selected)} Dateien (je ≤ {max_bytes_per_file} Bytes, gekürzt)._"
    return header + ("\n\n" + "\n".join(parts) if parts else "\n\n_(keine Inhalte gefunden)_")


# ---------------- OpenAI (Responses API) ----------------
DEFAULT_API_TIMEOUT = 1800.0
DEFAULT_API_MAX_RETRIES = 2
DEFAULT_API_POLL_INTERVAL = 1.5
DEFAULT_API_REQUEST_TIMEOUT = 30.0


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _extract_response_text(parts: Optional[Iterable[object]]) -> str:
    if not parts:
        return ""
    chunks: List[str] = []
    for item in parts:
        if isinstance(item, dict):
            item_type = item.get("type")
            content = item.get("content")
        else:
            item_type = getattr(item, "type", None)
            content = getattr(item, "content", None)
        if item_type == "message":
            if not content:
                continue
            for segment in content:
                if isinstance(segment, dict):
                    segment_type = segment.get("type")
                    text = segment.get("text", "")
                else:
                    segment_type = getattr(segment, "type", None)
                    text = getattr(segment, "text", "")
                if segment_type == "output_text":
                    if text:
                        chunks.append(text)
        elif item_type == "output_text":  # defensive: flattened content
            text = item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
            if text:
                chunks.append(text)
    return "".join(chunks)


def call_code_model(system: str, user: str) -> dict:
    """
    Ruft GPT-5-Codex (oder kompatibles Modell) über die Responses API auf.
    Ohne `response_format` (kompatibel mit aktuellen SDKs); wir parsen JSON aus output_text.
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    timeout = _env_float("OPENAI_API_TIMEOUT", DEFAULT_API_TIMEOUT)
    max_retries = _env_int("OPENAI_API_MAX_RETRIES", DEFAULT_API_MAX_RETRIES)
    poll_interval = max(0.2, _env_float("OPENAI_API_POLL_INTERVAL", DEFAULT_API_POLL_INTERVAL))
    request_timeout = max(1.0, _env_float("OPENAI_API_REQUEST_TIMEOUT", DEFAULT_API_REQUEST_TIMEOUT))
    if max_retries < 1:
        max_retries = 1

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            deadline = time.monotonic() + timeout
            response = client.responses.create(
                model="gpt-5-codex",
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                background=True,
                timeout=min(request_timeout, timeout),
            )

            response_id = getattr(response, "id", None)
            status = getattr(response, "status", None)
            while status in (None, "queued", "in_progress"):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("LLM call exceeded configured timeout")
                time.sleep(min(poll_interval, remaining))
                if not response_id:
                    break
                response = client.responses.retrieve(
                    response_id,
                    timeout=min(request_timeout, max(remaining, 0.1)),
                )
                status = getattr(response, "status", None)

            if status == "completed":
                text = getattr(response, "output_text", None)
                if not text:
                    text = _extract_response_text(getattr(response, "output", None))
                try:
                    return json.loads(text) if text else {}
                except Exception:
                    return {}

            if status == "failed" and getattr(response, "error", None):
                err = getattr(response, "error")
                message = getattr(err, "message", repr(err))
                raise RuntimeError(f"Model response failed: {message}")

            raise RuntimeError(f"Model response did not complete (status={status})")
        except Exception as exc:  # pragma: no cover - defensive logging
            last_error = exc
            print(
                f"OpenAI call attempt {attempt}/{max_retries} failed: {exc}",
                file=sys.stderr,
            )
            if attempt < max_retries:
                sleep_seconds = min(2 ** (attempt - 1), 5)
                time.sleep(sleep_seconds)

    if last_error:
        raise last_error
    return {}


def apply_plan(plan: dict) -> None:
    """Schreibt vom Modell gelieferte Patches/Tests ins Repo."""
    for p in plan.get("code_patches", []) or []:
        write(p["path"], p["content"])
    for t in plan.get("new_tests", []) or []:
        write(t["path"], t["content"])


def load_available_tasks(tasks_dir: pathlib.Path | str = DEFAULT_TASKS_DIR) -> List[TaskSpec]:
    """Load TaskSpec definitions from *tasks_dir* and cache them for selection."""

    path = pathlib.Path(tasks_dir)
    try:
        specs = load_task_specs(path)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise TaskContextError(path, str(exc)) from exc
    except TaskSpecLoadingError as exc:
        raise TaskContextError(exc.path, str(exc)) from exc

    _TASK_CATALOG.clear()
    _TASK_CATALOG.update({spec.task_id: spec for spec in specs})
    return specs


def _prepare_task_prompt() -> Optional[TaskPrompt]:
    try:
        return load_task_prompt(DEFAULT_TASKS_DIR)
    except TaskContextError as exc:
        append_event(
            level="error",
            source="task_context",
            message="Failed to load task prompt",
            details={"error": str(exc)},
        )
        return None


def _resolve_task_spec(task_id: str) -> Optional[TaskSpec]:
    """Return the cached TaskSpec for *task_id*, if available."""

    return _TASK_CATALOG.get(task_id)


def _select_task_for_execution(task_prompt: TaskPrompt) -> Optional[TaskSpec]:
    """Choose the highest-priority ready task whose dependencies are satisfied."""

    if not task_prompt.ready:
        return None

    ready_specs = [
        _resolve_task_spec(spec.task_id) or spec for spec in task_prompt.ready
    ]
    completed_ids = set(task_prompt.completed)
    return select_next_task(ready_specs, completed=completed_ids)


def _format_task_prompt_section(task_prompt: TaskPrompt) -> str:
    ready_summary = summarise_tasks_for_prompt(task_prompt.ready, limit=5)
    sections = [
        "## Task Backlog",
        task_prompt.prompt.strip(),
        ready_summary,
    ]
    return "\n\n".join(part for part in sections if part).strip()


def _format_selected_task_section(task: TaskSpec) -> str:
    """Render the selected TaskSpec in a structured markdown section."""

    lines: List[str] = [
        f"### Task ID: {task.task_id}",
        f"**Title:** {task.title}",
        f"**Summary:** {task.summary}",
        f"**Priority:** {task.priority or 'unspecified'}",
    ]

    if task.details:
        lines.extend(["", task.details.strip()])

    if task.context:
        lines.append("")
        lines.append("**Context references:**")
        lines.extend(f"- {entry}" for entry in task.context)

    if task.acceptance_criteria:
        lines.append("")
        lines.append("**Acceptance criteria:**")
        lines.extend(f"- {criterion}" for criterion in task.acceptance_criteria)

    if task.dependencies:
        deps = ", ".join(task.dependencies)
        lines.append("")
        lines.append(f"**Dependencies:** {deps}")

    if task.tags:
        tags = ", ".join(task.tags)
        lines.append("")
        lines.append(f"**Tags:** {tags}")

    return "\n".join(lines).strip()


def _inject_prompt_sections(
    template: str,
    *,
    backlog_section: str,
    selected_section: str,
    snapshot: str,
) -> str:
    """Return the final user prompt with backlog, selected task, and snapshot."""

    user = template
    if "{{task_prompt}}" in user:
        user = user.replace("{{task_prompt}}", backlog_section)
    else:
        user = user + "\n\n" + backlog_section

    if "{{selected_task}}" in user:
        user = user.replace("{{selected_task}}", selected_section)
    else:
        user = user + "\n\n## Selected Task\n" + selected_section

    if "{{repo_snapshot}}" in user:
        return user.replace("{{repo_snapshot}}", snapshot)

    return user + "\n\n---\n## Repository snapshot (truncated)\n" + snapshot


# ---------------- Checks ----------------
def run_local_checks() -> None:
    """Placeholder hook for optional local validation."""
    append_event(
        level="info",
        source="checks",
        message="Local quality gates are disabled; skipping checks.",
    )


# ---------------- GitHub API (PR) ----------------
def gh_api(method: str, path: str, data: Optional[dict] = None) -> dict:
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        print("GITHUB_REPOSITORY oder GITHUB_TOKEN nicht gesetzt; PR wird evtl. nicht automatisch erstellt.")
        return {}
    import urllib.request

    url = f"https://api.github.com/repos/{repo}{path}"
    req = urllib.request.Request(url, method=method.upper())
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, body) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        append_event(
            level="error",
            source="github_api",
            message="GitHub API request failed",
            details={"method": method, "path": path, "error": str(e)},
        )
        print(f"GitHub API error: {e}", file=sys.stderr)
        return {}


def ensure_label_auto() -> None:
    gh_api(
        "POST",
        "/labels",
        {
            "name": AUTO_LABEL,
            "color": "0E8A16",
            "description": "Auto-merge on green checks",
        },
    )


def ensure_auto_branch(branch: str) -> None:
    if not branch.startswith(AUTO_BRANCH_PREFIX):
        raise ValueError(
            "Auto-Merge benötigt Branches mit Präfix 'auto/'."
            " Bitte Skript nicht auf manuelle Branches anwenden."
        )


def apply_auto_label(pr_number: int) -> None:
    ensure_label_auto()
    gh_api("POST", f"/issues/{pr_number}/labels", {"labels": [AUTO_LABEL]})


def create_pull_request(branch: str, *, title: str, body: str) -> Optional[int]:
    try:
        ensure_auto_branch(branch)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None
    repo_info = gh_api("GET", "")
    base = repo_info.get("default_branch", "main") if repo_info else "main"
    pr = gh_api(
        "POST",
        "/pulls",
        {
            "title": title,
            "body": body,
            "head": branch,
            "base": base,
            "maintainer_can_modify": True,
            "draft": False,
        },
    )
    number = pr.get("number") if isinstance(pr, dict) else None
    if number:
        apply_auto_label(number)
        print(f"PR erstellt: #{number}")
        return number
    print("PR konnte nicht erstellt werden (fehlende Token/Permissions?).", file=sys.stderr)
    return None


# ---------------- Main ----------------
def main() -> int:
    ensure_git_identity()

    try:
        load_available_tasks(DEFAULT_TASKS_DIR)
    except TaskContextError as exc:
        append_event(
            level="error",
            source="orchestrator",
            message="Failed to load task specifications",
            details={"error": str(exc), "path": str(exc.path)},
        )
        print(f"Failed to load task specifications: {exc}", file=sys.stderr)
        return 1

    task_prompt = _prepare_task_prompt()
    if task_prompt is None:
        return 1
    if not task_prompt.prompt.strip() or task_prompt.is_empty():
        append_event(
            level="warning",
            source="orchestrator",
            message="No task prompt available; skipping orchestration run.",
        )
        return 0
    if not task_prompt.has_ready_tasks():
        append_event(
            level="info",
            source="orchestrator",
            message="No ready tasks available; nothing to execute.",
            details={"blocked_task_ids": [spec.task_id for spec in task_prompt.blocked]},
        )
        return 0

    primary_task = _select_task_for_execution(task_prompt)
    if primary_task is None:
        append_event(
            level="info",
            source="orchestrator",
            message="No eligible task found after evaluating ready queue.",
            details={
                "ready_task_ids": [spec.task_id for spec in task_prompt.ready],
                "completed_task_ids": list(task_prompt.completed),
            },
        )
        return 0
    plan_applied = False
    branch: Optional[str] = None
    try:
        system = (ROOT / "agent/prompts/system.md").read_text(encoding="utf-8")
        template = (ROOT / "agent/prompts/task_template.md").read_text(encoding="utf-8")

        backlog_section = _format_task_prompt_section(task_prompt)
        snapshot = build_repo_snapshot()
        selected_section = _format_selected_task_section(primary_task)
        user = _inject_prompt_sections(
            template,
            backlog_section=backlog_section,
            selected_section=selected_section,
            snapshot=snapshot,
        )

        plan = call_code_model(system, user)
        if isinstance(plan, dict) and (plan.get("code_patches") or plan.get("new_tests")):
            branch = create_branch()
            apply_plan(plan)
            plan_applied = True
        else:
            append_event(
                level="warning",
                source="orchestrator",
                message="LLM produced no actionable patches; leaving repository unchanged.",
            )
            return 0
    except Exception as e:
        append_event(
            level="error",
            source="orchestrator",
            message="LLM call failed",
            details={"error": str(e)},
        )
        print(f"LLM call failed: {e}", file=sys.stderr)
        sh(["git", "checkout", "-"], check=False)
        return 1

    if not plan_applied:
        return 0

    if branch is None:
        branch = create_branch()

    commit_message = f"feat: {primary_task.title}"
    commit_all(commit_message)
    try:
        run_local_checks()
    except Exception as e:
        append_event(
            level="error",
            source="orchestrator",
            message="Quality checks failed",
            details={"error": str(e)},
        )
        print(f"Tests fehlgeschlagen, kein Push/PR. Fehler: {e}", file=sys.stderr)
        sh(["git", "checkout", "-"], check=False)
        return 1

    push_branch(branch)
    pr_title = f"{primary_task.title} (auto)"
    pr_body = primary_task.summary
    create_pull_request(branch, title=pr_title, body=pr_body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
