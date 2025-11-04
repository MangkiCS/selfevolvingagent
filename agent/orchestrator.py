#!/usr/bin/env python3
"""
Orchestrator MVP (secure subprocess):
- erzeugt Feature-Branch auto/YYYYMMDD-HHMMSS
- schreibt Beispielcode + Tests, committet, pusht
- erstellt PR via GitHub API, vergibt Label 'auto'
- führt pytest lokal aus, bevor gepusht wird
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
from typing import Optional
from openai import OpenAI

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sh(args: list[str], check: bool = True, cwd: pathlib.Path = ROOT) -> str:
    """Sichere Shell: kein shell=True, Übergabe als Argumentliste."""
    print(f"$ {' '.join(args)}")
    res = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        # stderr auch ausgeben (hilft in Actions-Logs)
        print(res.stderr, file=sys.stderr)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}")
    return res.stdout.strip()


def write(path: str, content: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def ensure_git_identity() -> None:
    # Setze sichere Defaults (überschreibt nur, wenn leer)
    sh(["git", "config", "user.email", "actions@github.com"], check=False)
    sh(["git", "config", "user.name", "github-actions[bot]"], check=False)


def create_branch() -> str:
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    branch = f"auto/{ts}"
    sh(["git", "checkout", "-b", branch])
    return branch

def call_code_model(system: str, user: str):
    """
    Ruft GPT-5-Codex über die Responses API auf und erwartet strikt JSON.
    Setze OPENAI_API_KEY als Secret in GitHub (Settings → Secrets → Actions).
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.responses.create(
        model="gpt-5-codex",
        input=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user}
        ],
        temperature=0.2,
        response_format={"type": "json_object"},  # zwingt valides JSON
    )
    # Je nach SDK-Version:
    raw = getattr(resp, "output_text", None) or resp.output[0].content[0].text
    return json.loads(raw)


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
    write(
        "tests/test_hello.py",
        '''from agent.core.hello import say_hello

def test_say_hello():
    assert say_hello("World") == "Hello, World!"
''',
    )


def run_local_checks() -> None:
    # Style auto-fixen, dann committen falls Änderungen
    sh(["ruff", "check", "--fix", "."], check=False)
    sh(["git", "add", "-A"], check=False)
    sh(["git", "commit", "-m", "style(auto): ruff --fix"], check=False)

    # Typing/Security als Warnung lokal
    sh(["mypy", "."], check=False)
    # Nur High-Severity betrachten (Policy: fail on High)
    sh(["bandit", "-r", ".", "-lll"], check=False)

    # Tests mit Coverage-Gate (hartes Gate)
    sh(
        [
            "pytest",
            "-q",
            "--maxfail=1",
            "--disable-warnings",
            "--cov=.",
            "--cov-config=.config/coverage.toml",
        ],
        check=True,
    )


def commit_all(msg: str) -> None:
    sh(["git", "add", "-A"])
    sh(["git", "commit", "-m", msg])


def push_branch(branch: str) -> None:
    sh(["git", "push", "-u", "origin", branch])


def gh_api(method: str, path: str, data: Optional[dict] = None) -> dict:
    """Kleiner GitHub-API-Helper (nutzt das GITHUB_TOKEN aus der Action)."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        print(
            "GITHUB_REPOSITORY oder GITHUB_TOKEN nicht gesetzt; PR wird evtl. nicht automatisch erstellt."
        )
        return {}
    import urllib.request

    url = f"https://api.github.com/repos/{repo}{path}"
    req = urllib.request.Request(url, method=method.upper())
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, body_bytes) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"GitHub API error: {e}", file=sys.stderr)
        return {}


def ensure_label_auto() -> None:
    gh_api(
        "POST",
        "/labels",
        {"name": "auto", "color": "0E8A16", "description": "Auto-merge on green checks"},
    )


def create_pull_request(branch: str) -> Optional[int]:
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
        ensure_label_auto()
        gh_api("POST", f"/issues/{number}/labels", {"labels": ["auto"]})
        print(f"PR erstellt: #{number}")
        return number
    print("PR konnte nicht erstellt werden (fehlende Token/Permissions?).", file=sys.stderr)
    return None


def apply_plan(plan: dict) -> None:
    """Schreibt vom Modell gelieferte Patches/Tests ins Repo."""
    for p in plan.get("code_patches", []):
        write(p["path"], p["content"])
    for t in plan.get("new_tests", []):
        write(t["path"], t["content"])


def main() -> int:
    ensure_git_identity()
    branch = create_branch()

    # --- LLM-Call mit Prompts (optional) ---
    used_llm = False
    try:
        system = (ROOT / "agent/prompts/system.md").read_text(encoding="utf-8")
        user = (ROOT / "agent/prompts/task_template.md").read_text(encoding="utf-8")
        plan = call_code_model(system, user)  # <- jetzt mit Argumenten
        if isinstance(plan, dict) and (plan.get("code_patches") or plan.get("new_tests")):
            apply_plan(plan)
            used_llm = True
    except Exception as e:
        print(f"LLM call failed; fallback to example code: {e}", file=sys.stderr)

    # --- Fallback falls LLM nichts geliefert hat ---
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
