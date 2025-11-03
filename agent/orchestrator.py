#!/usr/bin/env python3
"""
Orchestrator MVP:
- erzeugt Feature-Branch auto/YYYYMMDD-HHMMSS
- schreibt Beispielcode + Tests, committet, pusht
- erstellt PR via GitHub API, vergibt Label 'auto'
- führt (optional) pytest lokal aus, bevor gepusht wird
"""
import os, subprocess, pathlib, datetime, json, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

def sh(cmd: str, cwd: pathlib.Path = ROOT, check: bool = True) -> str:
    print(f"$ {cmd}")
    res = subprocess.run(cmd, cwd=str(cwd), shell=True, capture_output=True, text=True)
    if check and res.returncode != 0:
        print(res.stdout)
        print(res.stderr)
        raise RuntimeError(f"Command failed: {cmd}")
    return res.stdout.strip()

def write(path: str, content: str):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

def ensure_git_identity():
    try:
        sh("git config user.email", check=False)
        sh("git config user.name", check=False)
    except Exception:
        pass
    # Setze sichere Defaults (wir überschreiben still, falls leer)
    sh('git config user.email "actions@github.com"', check=False)
    sh('git config user.name "github-actions[bot]"', check=False)

def create_branch() -> str:
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    branch = f"auto/{ts}"
    sh(f"git checkout -b {branch}")
    return branch

def add_example_code():
    # simple package structure
    write("agent/__init__.py", "")
    write("agent/core/__init__.py", "")
    write("agent/core/hello.py", '''"""Core hello util""" 
from typing import Final

GREETING: Final[str] = "Hello"

def say_hello(name: str) -> str:
    return f"{GREETING}, {name}!"
''')
    write("tests/test_hello.py", '''from agent.core.hello import say_hello

def test_say_hello():
    assert say_hello("World") == "Hello, World!"
''')

def run_local_checks():
    # Lint/Type/Security sind nice-to-have; pytest muss grün sein
    try:
        sh("ruff check .", check=False)
        sh("mypy .", check=False)
        sh("bandit -r .", check=False)
    except Exception:
        pass
    sh("pytest -q --maxfail=1 --disable-warnings --cov=.", check=True)

def commit_all(msg: str):
    sh("git add -A")
    sh(f"git commit -m \"{msg}\"")

def push_branch(branch: str):
    # In GitHub Actions ist 'origin' bereits mit Token konfiguriert.
    # Lokal reicht ein normaler Push mit SSH.
    sh(f"git push -u origin {branch}")

def gh_api(method: str, path: str, data: dict | None = None) -> dict:
    repo = os.environ.get("GITHUB_REPOSITORY")  # e.g. "MangkiCS/selfevolvingagent"
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        print("GITHUB_REPOSITORY oder GITHUB_TOKEN nicht gesetzt; PR wird evtl. nicht automatisch erstellt.")
        return {}
    import urllib.request
    url = f"https://api.github.com/repos/{repo}{path}"
    req = urllib.request.Request(url, method=method.upper())
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    else:
        body = None
    try:
        with urllib.request.urlopen(req, body) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"GitHub API error: {e}")
        return {}

def ensure_label_auto():
    # versuche Label 'auto' zu erstellen; ignoriere Fehler, falls es existiert
    gh_api("POST", "/labels", {"name": "auto", "color": "0E8A16", "description": "Auto-merge on green checks"})

def create_pull_request(branch: str) -> int | None:
    # PR von branch -> default branch (meist 'main')
    # Hole Default-Branch:
    repo_info = gh_api("GET", "")
    base = repo_info.get("default_branch", "main") if repo_info else "main"
    pr = gh_api("POST", "/pulls", {
        "title": "feat(core): add hello util (auto)",
        "body": "Automatisch generierter Patch: neue Funktion und Test.",
        "head": branch,
        "base": base,
        "maintainer_can_modify": True,
        "draft": False,
    })
    number = pr.get("number")
    if number:
        # Label hinzufügen
        ensure_label_auto()
        gh_api("POST", f"/issues/{number}/labels", {"labels": ["auto"]})
        print(f"PR erstellt: #{number}")
        return number
    print("PR konnte nicht erstellt werden (fehlende Token/Permissions?).")
    return None

def main():
    ensure_git_identity()
    branch = create_branch()
    add_example_code()
    # commit in zwei Schritten, damit diffs klar sind
    commit_all("feat(core): add hello util")
    try:
        run_local_checks()  # pytest & Co
    except Exception as e:
        print(f"Tests fehlgeschlagen, kein Push/PR. Fehler: {e}")
        # Wieder zurück auf main und Abbruch
        sh("git checkout -")
        return 1
    push_branch(branch)
    create_pull_request(branch)
    return 0

if __name__ == "__main__":
    sys.exit(main())
