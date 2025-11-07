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
import re
import subprocess
import sys
from typing import Dict, List, Optional, Sequence

from openai import OpenAI

from agent.core.event_log import append_event
from agent.core.pipeline import (
    ContextClue,
    ContextSummary,
    ExecutionPlan,
    RetrievalBrief,
    run_context_summary,
    run_execution_plan,
    run_retrieval_brief,
)
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

# Optional override for the next auto branch name.
_PREFERRED_BRANCH_NAME: Optional[str] = None

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
    global _PREFERRED_BRANCH_NAME
    if _PREFERRED_BRANCH_NAME:
        branch = _PREFERRED_BRANCH_NAME
    else:
        ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        branch = f"{AUTO_BRANCH_PREFIX}{ts}"
    sh(["git", "checkout", "-b", branch])
    _PREFERRED_BRANCH_NAME = None
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
def apply_plan(plan: ExecutionPlan) -> None:
    """Schreibt vom Modell gelieferte Patches/Tests ins Repo."""

    for patch in plan.code_patches:
        write(patch["path"], patch["content"])
    for test in plan.new_tests:
        write(test["path"], test["content"])


def load_available_tasks() -> List[TaskSpec]:
    """Load TaskSpec definitions from the default repository tasks directory."""

    path = pathlib.Path(DEFAULT_TASKS_DIR)
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
        task_prompt = load_task_prompt(DEFAULT_TASKS_DIR)
    except TaskContextError as exc:
        append_event(
            level="error",
            source="task_context",
            message="Failed to load task prompt",
            details={"error": str(exc)},
        )
        raise

    if not task_prompt.prompt.strip() or task_prompt.is_empty():
        append_event(
            level="warning",
            source="orchestrator",
            message="No task prompt available; skipping orchestration run.",
        )
        return None

    if not task_prompt.has_ready_tasks():
        append_event(
            level="info",
            source="orchestrator",
            message="No ready tasks available; nothing to execute.",
            details={"blocked_task_ids": [spec.task_id for spec in task_prompt.blocked]},
        )
        return None

    return task_prompt


def _resolve_task_spec(task_id: str) -> Optional[TaskSpec]:
    """Return the cached TaskSpec for *task_id*, if available."""

    return _TASK_CATALOG.get(task_id)


def _select_task_for_execution(task_prompt: TaskPrompt) -> Optional[TaskSpec]:
    """Choose the highest-priority ready task whose dependencies are satisfied."""

    if not task_prompt.ready:
        append_event(
            level="info",
            source="orchestrator",
            message="Ready queue empty; no task selected.",
        )
        return None

    resolved_ready: List[TaskSpec] = []
    missing_catalog_entries: List[str] = []
    for spec in task_prompt.ready:
        cached = _resolve_task_spec(spec.task_id)
        if cached is None:
            missing_catalog_entries.append(spec.task_id)
            resolved_ready.append(spec)
        else:
            resolved_ready.append(cached)

    if missing_catalog_entries:
        append_event(
            level="warning",
            source="orchestrator",
            message="Ready tasks missing from in-memory catalog; using prompt payload.",
            details={"missing_task_ids": missing_catalog_entries},
        )

    completed_ids = set(task_prompt.completed)
    task = select_next_task(resolved_ready, completed=completed_ids)
    if task is None:
        append_event(
            level="info",
            source="orchestrator",
            message="No eligible task found after evaluating ready queue.",
            details={
                "ready_task_ids": [spec.task_id for spec in task_prompt.ready],
                "completed_task_ids": list(task_prompt.completed),
            },
        )
    return task


def _slugify_task_identifier(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "task"


def _derive_task_metadata(task: TaskSpec) -> Dict[str, str]:
    slug = _slugify_task_identifier(task.task_id)
    branch = f"{AUTO_BRANCH_PREFIX}{slug}"
    commit_message = f"feat: {task.title}"
    pr_title = f"{task.title} (auto)"
    pr_body = task.summary
    return {
        "branch": branch,
        "commit_message": commit_message,
        "pr_title": pr_title,
        "pr_body": pr_body,
    }


def _checkout_branch_for_task(branch: str) -> str:
    global _PREFERRED_BRANCH_NAME
    previous = _PREFERRED_BRANCH_NAME
    _PREFERRED_BRANCH_NAME = branch
    try:
        return create_branch()
    finally:
        if previous is not None:
            _PREFERRED_BRANCH_NAME = previous


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


def _build_context_summary_prompt(task_prompt: TaskPrompt, task: TaskSpec) -> str:
    backlog_section = _format_task_prompt_section(task_prompt)
    selected_section = _format_selected_task_section(task)
    snapshot = build_repo_snapshot()
    instructions = (
        "# Context summarisation stage\n"
        "You will receive backlog context, the selected task, and a truncated repository snapshot. "
        "Summarise only the information necessary to plan retrieval for a downstream coding model.\n\n"
        "Return JSON with the following keys:\n"
        "- `summary`: concise narrative (<= 300 words) describing the task objective, constraints, and any critical implementation details.\n"
        "- `context_clues`: array (max 5) of objects with `id`, `path` (optional), `rationale`, and `content` (<= 500 characters, copy directly from the provided material when referencing code).\n"
        "Ensure clue ids follow the format `clue-1`, `clue-2`, ... for downstream reference."
    )
    sections = [
        instructions,
        "\n## Task Backlog\n" + backlog_section,
        "\n## Selected Task\n" + selected_section,
        "\n## Repository Snapshot (truncated)\n" + snapshot,
    ]
    return "\n".join(sections)


def _context_clues_to_json(clues: Sequence[ContextClue]) -> str:
    payload = [
        {
            "id": clue.identifier,
            "path": clue.path,
            "rationale": clue.rationale,
            "content": clue.content,
        }
        for clue in clues
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_retrieval_prompt(task: TaskSpec, context_summary: ContextSummary) -> str:
    selected_section = _format_selected_task_section(task)
    clues_json = _context_clues_to_json(context_summary.context_clues)
    instructions = (
        "# Retrieval brief stage\n"
        "You will receive a context summary and candidate context clues extracted from the repository snapshot. "
        "Select the minimal information required for the coding stage and produce a focused retrieval brief.\n\n"
        "Return JSON with the following keys:\n"
        "- `brief`: actionable summary to guide implementation (<= 200 words).\n"
        "- `selected_context_ids`: array of clue ids to forward to the coding model.\n"
        "- `focus_paths`: array of repository paths the coding model should inspect or modify.\n"
        "- `handoff_notes`: optional additional guidance for the coding stage.\n"
        "- `open_questions`: optional array of clarifications still needed."
    )
    summary_text = context_summary.summary or "(no summary provided)"
    clues_block = clues_json if clues_json.strip() else "[]"
    sections = [
        instructions,
        "\n## Selected Task (for reference)\n" + selected_section,
        "\n## Context Summary\n" + summary_text,
        "\n## Candidate Context Clues\n```json\n" + clues_block + "\n```",
    ]
    return "\n".join(sections)


def _format_context_clues(clues: Sequence[ContextClue]) -> str:
    if not clues:
        return "_No contextual excerpts were selected._"
    parts: List[str] = []
    for clue in clues:
        header = f"### {clue.identifier} — {clue.path or 'context'}"
        rationale = clue.rationale or "(no rationale provided)"
        excerpt = clue.content or "(no excerpt provided)"
        parts.extend(
            [
                header,
                f"*Why it matters:* {rationale}",
                "```text",
                excerpt,
                "```",
            ]
        )
    return "\n".join(parts)


def _select_context_clues(
    context_summary: ContextSummary, retrieval_brief: RetrievalBrief
) -> List[ContextClue]:
    if not context_summary.context_clues:
        return []
    if not retrieval_brief.selected_context_ids:
        return list(context_summary.context_clues)
    selected_ids = set(retrieval_brief.selected_context_ids)
    selected = [
        clue for clue in context_summary.context_clues if clue.identifier in selected_ids
    ]
    return selected or list(context_summary.context_clues)


def _build_execution_prompt(
    task: TaskSpec,
    retrieval_brief: RetrievalBrief,
    context_clues: Sequence[ContextClue],
) -> str:
    selected_section = _format_selected_task_section(task)
    context_section = _format_context_clues(context_clues)
    focus_paths = retrieval_brief.focus_paths or []
    focus_block = "\n".join(f"- {path}" for path in focus_paths) or "- (no specific paths provided)"
    open_questions = retrieval_brief.open_questions or []
    questions_block = (
        "\n".join(f"- {question}" for question in open_questions)
        if open_questions
        else "- (none)"
    )
    instructions = (
        "# Implementation stage\n"
        "Use the retrieval brief and selected context to produce an actionable execution plan. "
        "Respond with JSON containing `rationale`, `plan` (array of steps), `code_patches`, `new_tests`, `admin_requests`, and optional `notes`.\n"
        "- `code_patches` entries must include `path` and full file `content`.\n"
        "- Limit the scope to the provided focus paths unless the plan justifies additional files."
    )
    sections = [
        instructions,
        "\n## Selected Task\n" + selected_section,
        "\n## Retrieval Brief\n" + (retrieval_brief.brief or "(no brief provided)"),
        "\n## Focus Paths\n" + focus_block,
        "\n## Handoff Notes\n" + (retrieval_brief.handoff_notes or "(none)"),
        "\n## Open Questions\n" + questions_block,
        "\n## Context Excerpts\n" + context_section,
    ]
    return "\n".join(sections)


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
        load_available_tasks()
    except TaskContextError as exc:
        append_event(
            level="error",
            source="orchestrator",
            message="Failed to load task specifications",
            details={"error": str(exc), "path": str(exc.path)},
        )
        print(f"Failed to load task specifications: {exc}", file=sys.stderr)
        return 1

    try:
        task_prompt = _prepare_task_prompt()
    except TaskContextError as exc:
        print(f"Failed to prepare task prompt: {exc}", file=sys.stderr)
        return 1

    if task_prompt is None:
        return 0

    primary_task = _select_task_for_execution(task_prompt)
    if primary_task is None:
        return 0

    metadata = _derive_task_metadata(primary_task)
    branch_name = metadata["branch"]
    commit_message = metadata["commit_message"]
    pr_title = metadata["pr_title"]
    pr_body = metadata["pr_body"]

    plan_applied = False
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    try:
        system = (ROOT / "agent/prompts/system.md").read_text(encoding="utf-8")

        context_prompt = _build_context_summary_prompt(task_prompt, primary_task)
        context_summary = run_context_summary(client, system_prompt=system, user_prompt=context_prompt)

        retrieval_prompt = _build_retrieval_prompt(primary_task, context_summary)
        retrieval_brief = run_retrieval_brief(client, system_prompt=system, user_prompt=retrieval_prompt)

        selected_clues = _select_context_clues(context_summary, retrieval_brief)
        execution_prompt = _build_execution_prompt(primary_task, retrieval_brief, selected_clues)
        execution_plan = run_execution_plan(client, system_prompt=system, user_prompt=execution_prompt)

        if execution_plan.has_changes():
            branch_name = _checkout_branch_for_task(branch_name)
            apply_plan(execution_plan)
            plan_applied = True
        else:
            append_event(
                level="warning",
                source="orchestrator",
                message="LLM produced no actionable patches; leaving repository unchanged.",
                details={"stage": "execution_plan"},
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

    push_branch(branch_name)
    create_pull_request(branch_name, title=pr_title, body=pr_body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
