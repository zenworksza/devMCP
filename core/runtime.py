from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path.home() / "workspaces"
SERVER_DIR = Path.home() / "mcp-dev-server"
MEMORY_FILE = SERVER_DIR / "memory.json"
REMOTE_FILE = SERVER_DIR / "remote_servers.json"
CACHE_FILE = SERVER_DIR / "file_cache.json"
TOOLS_FILE = SERVER_DIR / "tools_installed.json"
AGENTS_MD = SERVER_DIR / "AGENTS.md"

MAX_OUTPUT = 4000
MAX_LINES_FULL = 200
HEAD_LINES = 20
TAIL_LINES = 10

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SERVER_DIR.mkdir(parents=True, exist_ok=True)


def trim(text: str, label: str = "output", head_tail: bool = False) -> str:
    if len(text) <= MAX_OUTPUT:
        return text

    lines = text.splitlines()
    if head_tail and len(lines) > HEAD_LINES + TAIL_LINES:
        head = "\n".join(lines[:HEAD_LINES])
        tail = "\n".join(lines[-TAIL_LINES:])
        omitted = len(lines) - HEAD_LINES - TAIL_LINES
        return (
            f"{head}\n\n"
            f"[... {omitted} lines omitted - use read_file(start_line, end_line) "
            f"or search_files() to access specific sections ...]\n\n"
            f"{tail}"
        )

    kept = text[:MAX_OUTPUT]
    lines_cut = text[MAX_OUTPUT:].count("\n")
    return kept + f"\n\n[{label} trimmed - {lines_cut} more lines not shown. Use line ranges to narrow scope.]"


def tool_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = (
        f"{SERVER_DIR / '.venv' / 'bin'}:"
        "/home/mdb/.local/bin:"
        "/home/mdb/.npm-global/bin:"
        "/usr/local/bin:/usr/bin:/bin:"
        + env.get("PATH", "")
    )
    return env


def run_safe(
    cmd: list[str],
    cwd: str | None = None,
    label: str = "output",
    timeout: int = 60,
    head_tail: bool = False,
) -> str:
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=tool_env(),
        )
        return trim(result.stdout + result.stderr, label, head_tail=head_tail)
    except subprocess.TimeoutExpired:
        return f"[Timed out after {timeout}s: {' '.join(cmd)}]"
    except FileNotFoundError:
        return f"[Command not found: {cmd[0]}]"


def load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def load_memory() -> dict:
    return load_json(MEMORY_FILE)


def save_memory(data: dict) -> None:
    save_json(MEMORY_FILE, data)


def load_remotes() -> dict:
    return load_json(REMOTE_FILE)


def save_remotes(data: dict) -> None:
    save_json(REMOTE_FILE, data)


def load_cache() -> dict:
    return load_json(CACHE_FILE)


def save_cache(data: dict) -> None:
    save_json(CACHE_FILE, data)


def cmd_exists(cmd: str) -> bool:
    try:
        subprocess.run(["which", cmd], capture_output=True, check=True, env=tool_env())
        return True
    except subprocess.CalledProcessError:
        return False


def pip_install(*packages: str) -> str:
    venv_pip = SERVER_DIR / ".venv" / "bin" / "pip"
    pip_cmd = str(venv_pip) if venv_pip.exists() else "pip3"
    return run_safe([pip_cmd, "install", "--quiet", *packages], label="pip", timeout=120)


def npm_global(*packages: str) -> str:
    return run_safe(["npm", "install", "-g", "--quiet", *packages], label="npm", timeout=120)


def apt_install(*packages: str) -> str:
    return run_safe(["sudo", "apt-get", "install", "-y", "-qq", *packages], label="apt", timeout=120)


def ensure_tools() -> None:
    installed = load_json(TOOLS_FILE)
    changed = False

    def mark(tool: str, status: str) -> None:
        nonlocal changed
        installed[tool] = {"status": status, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        changed = True

    if not cmd_exists("rg"):
        apt_install("ripgrep")
        mark("ripgrep", "apt")
    if not cmd_exists("jq"):
        apt_install("jq")
        mark("jq", "apt")
    for pkg, cmd in [
        ("black", "black"),
        ("ruff", "ruff"),
        ("pylint", "pylint"),
        ("semgrep", "semgrep"),
        ("httpie", "http"),
    ]:
        if not cmd_exists(cmd):
            pip_install(pkg)
            mark(pkg, "pip")
    for pkg, cmd in [("prettier", "prettier"), ("eslint", "eslint")]:
        if not cmd_exists(cmd):
            npm_global(pkg)
            mark(pkg, "npm")
    if not cmd_exists("sg"):
        if cmd_exists("cargo"):
            run_safe(["cargo", "install", "ast-grep", "--quiet"], label="cargo", timeout=300)
        else:
            npm_global("@ast-grep/cli")
        mark("ast-grep", "installed")

    if changed:
        save_json(TOOLS_FILE, installed)


def telegram_send(message: str) -> str:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return "[Telegram not configured]"
    return run_safe(
        [
            "curl",
            "-s",
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            "-d",
            f"chat_id={TELEGRAM_CHAT_ID}",
            "-d",
            f"text={message}",
            "-d",
            "parse_mode=Markdown",
        ],
        label="telegram",
    )
