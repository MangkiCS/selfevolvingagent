#!/usr/bin/env python3
"""
Orchestrator MVP (secure subprocess):
- erzeugt Feature-Branch auto/YYYYMMDD-HHMMSS
- ruft optional ein Code-Modell (Responses API) auf
- schreibt Patches/Tests oder fällt auf Beispielcode zurück
- committet, pusht, erstellt PR + Label 'auto'
- führt pytest mit Coverage-Gate aus
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
from typing import List, Optional

from openai import OpenAI

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTO_BRANCH_PREFIX = "auto/"
AUTO_LABEL = "auto"


# ---------------- Shell helper (ohne shell=True) ----------------
def sh(args: List[str], check: bool = True, cwd: pathlib.Path = ROOT) -> str:
    print(f"$ {' '.join(args)}")
    res = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)
    if check and res.returncode != 0:
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


# ---------------- OpenAI (Responses API) ----------------
def call_code_model(system: str, user: str) -> dict:
    """
    Ruft GPT-5-Codex (oder kompatibles Modell) über die Responses API auf.
    Ohne `response_format` (kompatibel mit aktuellen SDKs); wir parsen JSON aus output_text.
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    resp = client.responses.create(
        model="gpt-5-codex",
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        # response_format weggelassen -> per Prompt striktes JSON verlangen
    )

    text = getattr(resp, "output_text", None)
    if not text:
        # Fallback: zusammensetzen, falls kein output_text vorhanden ist
        try:
            # resp.output ist eine Liste von Nachrichten/Teilen
            text = "".join(
                "".join(part.get("text", "") for part in item.get("content", []))  # type: ignore
                if isinstance(item, dict) else ""
                for item in getattr(resp, "output", [])
            )
        except Exception:
            text = ""

    try:
        return json.loads(text) if text else {}
    except Exception:
        # notfalls leeres Ergebnis -> Fallback greift
        return {}


def apply_plan(plan: dict) -> None:
    """Schreibt vom Modell gelieferte Patches/Tests ins Repo."""
    for p in plan.get("code_patches", []) or []:
        write(p["path"], p["content"])
    for t in plan.get("new_tests", []) or []:
        write(t["path"], t["content"])


# ---------------- Beispielcode (Fallback) ----------------
def add_example_code() -> None:
    write("agent/__init__.py", "")
    write("agent/core/__init__.py", "")
    write(
        "agent/core/hello.py",
        '''"""Core hello util"""
from typing import Final

GREETING: Final[str] = "Hello"

def say_hello(name: str) -> str:
    return f"{GREETING}, {name}!"
''',
    )
    # Build-Marker -> sorgt dafür, dass immer ein Commit entsteht
    ts = datetime.datetime.utcnow().isoformat()
    write("agent/core/buildinfo.py", f'BUILD_TS = "{ts}"\n')
    write(
        "tests/test_hello.py",
        '''from agent.core.hello import say_hello

def test_say_hello():
    assert say_hello("World") == "Hello, World!"
''',
    )


# ---------------- Checks ----------------
def run_local_checks() -> None:
    # Stil automatisch reparieren -> optional committen
    sh(["ruff", "check", "--fix", "."], check=False)
    sh(["git", "add", "-A"], check=False)
    sh(["git", "commit", "-m", "style(auto): ruff --fix"], check=False)

    # Typing/Security als Warnung lokal
    sh(["mypy", "."], check=False)
    # Nur High-Severity (Policy): Build darf bei High scheitern
    sh(["bandit", "-r", ".", "-lll"], check=False)

    # Tests mit Coverage-Gate (hart)
    sh(
        [
            "pytest",
            "-q",
            "--maxfail=1",
            "--disable-warnings",
            "--cov=.",
            "--cov-config=.config/coverage.toml",
        ]
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


def create_pull_request(branch: str) -> Optional[int]:
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
            "title": "feat(core): add hello util (auto)",
            "body": "Automatisch generierter Patch: neue Funktion und Test.",
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
    branch = create_branch()

    used_llm = False
    try:
        system = (ROOT / "agent/prompts/system.md").read_text(encoding="utf-8")
        user = (ROOT / "agent/prompts/task_template.md").read_text(encoding="utf-8")
        plan = call_code_model(system, user)
        if isinstance(plan, dict) and (plan.get("code_patches") or plan.get("new_tests")):
            apply_plan(plan)
            used_llm = True
    except Exception as e:
        print(f"LLM call failed; fallback to example code: {e}", file=sys.stderr)

    if not used_llm:
        add_example_code()

    commit_all("feat(core): add hello util")
    try:
        run_local_checks()
    except Exception as e:
        print(f"Tests fehlgeschlagen, kein Push/PR. Fehler: {e}", file=sys.stderr)
        sh(["git", "checkout", "-"], check=False)
        return 1

    push_branch(branch)
    create_pull_request(branch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
