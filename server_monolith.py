"""
MCP Dev Server — ~/mcp-dev-server/server.py

Token efficiency features:
  - File size gate: blocks full reads of files > 200 lines, forces surgical reads
  - file_outline(): returns class/function structure without content
  - task_start(): loads project context + prior memory before any task
  - Head/tail trim: large outputs show first+last lines with gap notice
  - File cache: mtime-aware, persisted, auto-invalidated on write_file
  - Dev toolset: auto-installed on first run
  - Telegram notifications
  - Per-project remote server registry
  - Agent router (Codex → Kimi/Gemini delegation)
"""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import subprocess
import json
import time
import os
import re

# ─── Config ───────────────────────────────────────────────────────────────────

PROJECT_ROOT     = Path.home() / "workspaces"
SERVER_DIR       = Path.home() / "mcp-dev-server"
MEMORY_FILE      = SERVER_DIR / "memory.json"
REMOTE_FILE      = SERVER_DIR / "remote_servers.json"
CACHE_FILE       = SERVER_DIR / "file_cache.json"
TOOLS_FILE       = SERVER_DIR / "tools_installed.json"
AGENTS_MD        = SERVER_DIR / "AGENTS.md"

MAX_OUTPUT       = 4000   # chars returned by any tool
MAX_LINES_FULL   = 200    # max lines before read_file requires a range
HEAD_LINES       = 20     # lines shown at start of trimmed output
TAIL_LINES       = 10     # lines shown at end of trimmed output

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SERVER_DIR.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("dev-server", host="0.0.0.0", port=8000)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def trim(text: str, label: str = "output", head_tail: bool = False) -> str:
    """
    Trim output to MAX_OUTPUT chars.
    head_tail=True: show first HEAD_LINES + last TAIL_LINES with gap notice.
    head_tail=False: truncate with line count notice.
    """
    if len(text) <= MAX_OUTPUT:
        return text

    lines = text.splitlines()

    if head_tail and len(lines) > HEAD_LINES + TAIL_LINES:
        head    = "\n".join(lines[:HEAD_LINES])
        tail    = "\n".join(lines[-TAIL_LINES:])
        omitted = len(lines) - HEAD_LINES - TAIL_LINES
        return (
            f"{head}\n\n"
            f"[... {omitted} lines omitted — use read_file(start_line, end_line) "
            f"or search_files() to access specific sections ...]\n\n"
            f"{tail}"
        )

    kept      = text[:MAX_OUTPUT]
    lines_cut = text[MAX_OUTPUT:].count("\n")
    return kept + f"\n\n[{label} trimmed — {lines_cut} more lines not shown. Use line ranges to narrow scope.]"


def run_safe(cmd: list[str], cwd: str | None = None, label: str = "output",
             timeout: int = 60, head_tail: bool = False) -> str:
    try:
        env = tool_env()
        result = subprocess.run(
            cmd,
            cwd=cwd or str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
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


def load_memory() -> dict:  return load_json(MEMORY_FILE)
def save_memory(d: dict):   save_json(MEMORY_FILE, d)
def load_remotes() -> dict: return load_json(REMOTE_FILE)
def save_remotes(d: dict):  save_json(REMOTE_FILE, d)
def load_cache() -> dict:   return load_json(CACHE_FILE)
def save_cache(d: dict):    save_json(CACHE_FILE, d)


# ─── Dev toolset: auto-install on startup ─────────────────────────────────────

def tool_env() -> dict:
    env = os.environ.copy()
    env["PATH"] = (
        f"{SERVER_DIR / '.venv' / 'bin'}:"
        "/home/mdb/.local/bin:"
        "/home/mdb/.npm-global/bin:"
        "/usr/local/bin:/usr/bin:/bin:"
        + env.get("PATH", "")
    )
    return env


def _cmd_exists(cmd: str) -> bool:
    try:
        subprocess.run(["which", cmd], capture_output=True, check=True, env=tool_env())
        return True
    except subprocess.CalledProcessError:
        return False


def _pip_install(*packages: str) -> str:
    venv_pip = SERVER_DIR / ".venv" / "bin" / "pip"
    pip_cmd  = str(venv_pip) if venv_pip.exists() else "pip3"
    return run_safe([pip_cmd, "install", "--quiet", *packages], label="pip", timeout=120)


def _npm_global(*packages: str) -> str:
    return run_safe(["npm", "install", "-g", "--quiet", *packages], label="npm", timeout=120)


def _apt_install(*packages: str) -> str:
    return run_safe(["sudo", "apt-get", "install", "-y", "-qq", *packages], label="apt", timeout=120)


def _ensure_tools():
    installed = load_json(TOOLS_FILE)
    changed   = False

    def mark(tool: str, status: str):
        nonlocal changed
        installed[tool] = {"status": status, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        changed = True

    if not _cmd_exists("rg"):
        _apt_install("ripgrep");       mark("ripgrep",  "apt")
    if not _cmd_exists("jq"):
        _apt_install("jq");            mark("jq",       "apt")
    for pkg, cmd in [("black","black"),("ruff","ruff"),("pylint","pylint"),
                     ("semgrep","semgrep"),("httpie","http")]:
        if not _cmd_exists(cmd):
            _pip_install(pkg);         mark(pkg, "pip")
    for pkg, cmd in [("prettier","prettier"),("eslint","eslint")]:
        if not _cmd_exists(cmd):
            _npm_global(pkg);          mark(pkg, "npm")
    if not _cmd_exists("sg"):
        if _cmd_exists("cargo"):
            run_safe(["cargo", "install", "ast-grep", "--quiet"], label="cargo", timeout=300)
        else:
            _npm_global("@ast-grep/cli")
        mark("ast-grep", "installed")

    if changed:
        save_json(TOOLS_FILE, installed)


try:
    _ensure_tools()
except Exception:
    pass


# ─── File cache ───────────────────────────────────────────────────────────────

def _cache_key(project: str, file_path: str) -> str:
    return f"{project}::{file_path}"


def _get_mtime(project: str, file_path: str) -> float:
    try:
        return (PROJECT_ROOT / project / file_path).stat().st_mtime
    except FileNotFoundError:
        return 0.0


def cache_get(project: str, file_path: str) -> str | None:
    cache = load_cache()
    key   = _cache_key(project, file_path)
    if key not in cache:
        return None
    entry = cache[key]
    if entry.get("mtime") != _get_mtime(project, file_path):
        del cache[key]
        save_cache(cache)
        return None
    return entry["content"]


def cache_set(project: str, file_path: str, content: str) -> None:
    cache = load_cache()
    cache[_cache_key(project, file_path)] = {
        "content": content,
        "mtime":   _get_mtime(project, file_path),
        "cached":  time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    save_cache(cache)


def cache_evict(project: str, file_path: str) -> None:
    cache = load_cache()
    key   = _cache_key(project, file_path)
    if key in cache:
        del cache[key]
        save_cache(cache)


# ─── Telegram ─────────────────────────────────────────────────────────────────

def _telegram_send(message: str) -> str:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return "[Telegram not configured]"
    return run_safe([
        "curl", "-s",
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        "-d", f"chat_id={TELEGRAM_CHAT_ID}",
        "-d", f"text={message}",
        "-d", "parse_mode=Markdown",
    ], label="telegram")


@mcp.tool()
def telegram_notify(message: str) -> str:
    """
    Send a Telegram message to the developer.
    Use to report task completion, errors, or to request approval.
    Include project name and what action is needed.
    """
    return _telegram_send(message)


# ─── Task start (token efficiency entry point) ────────────────────────────────

@mcp.tool()
def task_start(project: str, task_description: str) -> str:
    """
    CALL THIS FIRST before any task. Returns all context needed to work efficiently:
      - Project.md (stack, rules, key files, remote server)
      - Prior agent memory for this project
      - Reminder of token efficiency rules

    This prevents re-deriving context and eliminates redundant file reads.
    After calling this, use file_outline() before read_file().
    """
    sections = []
    # Load AGENTS.md operating manual
    if AGENTS_MD.exists():
        sections.append(f"=== Operating Manual (AGENTS.md) ===\n{AGENTS_MD.read_text()[:3000]}")
    # Project context
    found_project_md = False
    for name in ("Project.md", "PROJECT.md", "project.md"):
        path = PROJECT_ROOT / project / name
        if path.exists():
            content = path.read_text()
            sections.append(f"=== Project Context ({name}) ===\n{content[:3000]}")
            found_project_md = True
            break
    if not found_project_md:
        sections.append(
            f"[No Project.md found in {project}]\n"
            f"Create ~/workspaces/{project}/Project.md with stack, rules, key files, and remote info."
        )

    # Prior memory
    data     = load_memory()
    relevant = {k: v for k, v in data.items() if project.lower() in k.lower()}
    if relevant:
        sections.append("=== Prior Agent Work ===")
        for k, v in list(relevant.items())[:10]:  # cap at 10 entries
            sections.append(f"{k} (updated {v['updated']}):\n{v['value'][:400]}")
    else:
        sections.append("[No prior memory for this project — this may be a fresh task]")

    # Task
    sections.append(f"=== Your Task ===\n{task_description}")

    # Efficiency reminder
    sections.append(
        "=== Token Efficiency Rules ===\n"
        "1. Use file_outline() before read_file() — get structure first\n"
        "2. Use search_files() to locate code — never read whole dirs\n"
        "3. Use read_file(start_line, end_line) — never read >200 lines at once\n"
        "4. Save findings with memory_set() before finishing\n"
        "5. Use telegram_notify() to report completion"
    )

    return "\n\n".join(sections)


# ─── Project context ──────────────────────────────────────────────────────────

@mcp.tool()
def project_context(project: str) -> str:
    """
    Load Project.md for a project.
    Contains stack, rules, key files, and remote server details.
    Prefer task_start() which loads this plus memory in one call.
    """
    for name in ("Project.md", "PROJECT.md", "project.md"):
        path = PROJECT_ROOT / project / name
        if path.exists():
            return path.read_text()
    return (
        f"[No Project.md found in {project}]\n"
        f"Create ~/workspaces/{project}/Project.md to give agents project context."
    )


# ─── File tools (with cache + size gate) ─────────────────────────────────────

@mcp.tool()
def file_outline(project: str, file_path: str) -> str:
    """
    Return the structure of a file without its full content.
    Shows class/function definitions with line numbers.
    ALWAYS call this before read_file() on files you haven't read before.
    Use the line numbers returned to make precise read_file() calls.

    Python: class, def, async def
    JS/TS:  export, function, class, const arrow functions
    Other:  top-level non-indented lines
    """
    full_path = PROJECT_ROOT / project / file_path
    if not full_path.exists():
        return f"[File not found: {full_path}]"

    try:
        lines = full_path.read_text(errors="replace").splitlines()
        ext   = Path(file_path).suffix.lower()

        if ext == ".py":
            pattern = re.compile(r'^(class |def |async def )')
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            pattern = re.compile(r'^(export |function |class |const \w+ = )')
        elif ext in (".go",):
            pattern = re.compile(r'^(func |type |var |const )')
        elif ext in (".rs",):
            pattern = re.compile(r'^(pub |fn |struct |impl |enum |trait )')
        else:
            pattern = re.compile(r'^\S')

        hits = [
            f"L{i+1:4d}: {line.rstrip()}"
            for i, line in enumerate(lines)
            if pattern.match(line)
        ]

        if not hits:
            return f"{file_path} ({len(lines)} lines) — no top-level definitions found. Use read_file() directly."

        return f"{file_path} ({len(lines)} lines)\n\n" + "\n".join(hits)
    except Exception as e:
        return f"[Error reading file: {e}]"


@mcp.tool()
def read_file(project: str, file_path: str, start_line: int = 1, end_line: int = 0) -> str:
    """
    Read a file or specific line range from a project.

    IMPORTANT: For files over 200 lines, you MUST provide start_line and end_line.
    Call file_outline() first to find which lines you need.

    Cache: full-file reads are cached by mtime. Repeated reads of unchanged files
    are free. write_file() automatically invalidates the cache.

    end_line=0 means read to end of file (still subject to size gate).
    """
    full_path = PROJECT_ROOT / project / file_path
    if not full_path.exists():
        return f"[File not found: {full_path}]"

    try:
        raw   = full_path.read_text(errors="replace")
        lines = raw.splitlines()
        total = len(lines)

        # Size gate: full-file read on large files
        if start_line == 1 and end_line == 0 and total > MAX_LINES_FULL:
            return (
                f"[{file_path} has {total} lines — too large to read in full]\n\n"
                f"To read efficiently:\n"
                f"  1. Call file_outline('{project}', '{file_path}') to see structure\n"
                f"  2. Call read_file('{project}', '{file_path}', start_line=N, end_line=M) "
                f"for the section you need\n"
                f"  3. Or call search_files('{project}', 'pattern') to locate specific code"
            )

        # Cache full-file reads for small files
        if start_line == 1 and end_line == 0:
            cached = cache_get(project, file_path)
            if cached is not None:
                return f"[cache hit — {file_path}]\n{trim(cached, file_path)}"
            cache_set(project, file_path, raw)

        chunk   = lines[start_line - 1 : end_line if end_line > 0 else None]
        content = "\n".join(f"{i + start_line:4d}: {l}" for i, l in enumerate(chunk))
        return trim(content, file_path, head_tail=True)

    except Exception as e:
        return f"[Error reading file: {e}]"


@mcp.tool()
def write_file(project: str, file_path: str, content: str) -> str:
    """
    Write content to a file on disk and invalidate its cache entry.
    This is the ONLY correct way to make code changes.
    After writing: run lint(), then deploy_local() to apply changes.
    """
    full_path = PROJECT_ROOT / project / file_path
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        cache_evict(project, file_path)
        return f"[Written: {file_path} ({len(content)} chars, {len(content.splitlines())} lines) — cache invalidated]"
    except Exception as e:
        return f"[Error writing file: {e}]"


@mcp.tool()
def cache_list(project: str = "") -> str:
    """List cached files, optionally filtered by project."""
    cache   = load_cache()
    entries = [(k, v) for k, v in cache.items() if not project or k.startswith(f"{project}::")]
    if not entries:
        return "[No cached files]"
    lines = [f"{k}  (cached: {v['cached']})" for k, v in sorted(entries)]
    return f"{len(lines)} cached file(s):\n" + "\n".join(lines)


@mcp.tool()
def cache_invalidate(project: str, file_path: str) -> str:
    """Manually evict a file from the cache."""
    cache_evict(project, file_path)
    return f"[Cache invalidated: {project}::{file_path}]"


@mcp.tool()
def cache_clear(project: str = "") -> str:
    """Clear file cache for a project, or all projects if project is empty."""
    cache = load_cache()
    if project:
        keys = [k for k in cache if k.startswith(f"{project}::")]
        for k in keys:
            del cache[k]
        save_cache(cache)
        return f"[Cleared {len(keys)} cache entries for {project}]"
    count = len(cache)
    save_cache({})
    return f"[Cleared all {count} cache entries]"


@mcp.tool()
def search_files(project: str, pattern: str, file_glob: str = "") -> str:
    """
    Search project files for a pattern. Uses ripgrep (rg) if available.
    Use this INSTEAD of reading whole files to locate code.
    file_glob example: "*.py", "*.ts"

    Returns file paths and line numbers — use these with read_file(start_line, end_line).
    """
    path = str(PROJECT_ROOT / project)
    if _cmd_exists("rg"):
        cmd = ["rg", "--line-number", "--no-heading"]
        if file_glob:
            cmd += ["--glob", file_glob]
        cmd += [pattern, "."]
    else:
        cmd = ["grep", "-RIn", "--exclude-dir=.git", "--exclude-dir=node_modules"]
        if file_glob:
            cmd += [f"--include={file_glob}"]
        cmd += [pattern, "."]
    return run_safe(cmd, path, f"search '{pattern}'", head_tail=True)


# ─── Git tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def list_projects() -> str:
    """List available project folders in ~/workspaces."""
    if not PROJECT_ROOT.exists():
        return f"[workspaces not found at {PROJECT_ROOT}]"
    return "\n".join(p.name for p in sorted(PROJECT_ROOT.iterdir()) if p.is_dir())


@mcp.tool()
def git_status(project: str) -> str:
    """Show git status (short format)."""
    return run_safe(["git", "status", "--short"], str(PROJECT_ROOT / project), "git status")


@mcp.tool()
def git_diff(project: str, path_filter: str = "") -> str:
    """Show git diff. Use path_filter to limit to one file."""
    cmd = ["git", "diff"] + (["--", path_filter] if path_filter else [])
    return run_safe(cmd, str(PROJECT_ROOT / project), "git diff", head_tail=True)


@mcp.tool()
def git_log(project: str, n: int = 10) -> str:
    """Show last N commits (max 50), one line each."""
    return run_safe(["git", "log", "--oneline", f"-{min(n,50)}"],
                    str(PROJECT_ROOT / project), "git log")


@mcp.tool()
def git_pull(project: str) -> str:
    """Pull latest changes from remote."""
    return run_safe(["git", "pull"], str(PROJECT_ROOT / project), "git pull")


@mcp.tool()
def git_clone(repo_url: str, project_name: str) -> str:
    """Clone a repo into ~/workspaces/<project_name>."""
    return run_safe(["git", "clone", repo_url, project_name],
                    str(PROJECT_ROOT), "git clone", timeout=120)


@mcp.tool()
def git_push_staging(project: str, commit_message: str, pr_description: str = "") -> str:
    """
    Commit all changes, push to staging branch, notify via Telegram with PR link.
    ONLY call this after code is confirmed working via deploy_local() + http_request().
    Never push directly to main.
    """
    path = str(PROJECT_ROOT / project)
    run_safe(["git", "add", "-A"], path)
    commit_out = run_safe(["git", "commit", "-m", commit_message], path)
    if "nothing to commit" in commit_out:
        return "[Nothing to commit — working tree clean]"
    run_safe(["git", "checkout", "-B", "staging"], path)
    push_out = run_safe(["git", "push", "origin", "staging", "--force-with-lease"],
                        path, timeout=60)
    remote_url = run_safe(["git", "remote", "get-url", "origin"], path).strip()
    pr_link    = ""
    if "github.com" in remote_url:
        clean   = re.sub(r"git@github\.com:", "https://github.com/", remote_url).rstrip(".git")
        pr_link = f"{clean}/compare/staging?expand=1"
    msg = [f"✅ *{project}* — staging updated", f"📝 {commit_message}"]
    if pr_description:
        msg.append(f"_{pr_description}_")
    if pr_link:
        msg.append(f"🔗 [Open PR]({pr_link})")
    msg.append("👆 Please review and merge to main.")
    _telegram_send("\n".join(msg))
    return f"{commit_out}\n{push_out}\nTelegram notification sent."


# ─── Docker tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def docker_compose_ps(project: str) -> str:
    """Show docker compose service status."""
    return run_safe(["docker", "compose", "ps"], str(PROJECT_ROOT / project), "docker ps")


@mcp.tool()
def docker_compose_logs(project: str, service: str, lines: int = 50) -> str:
    """Show docker compose logs for one service (max 200 lines)."""
    return run_safe(
        ["docker", "compose", "logs", "--tail", str(min(lines, 200)), service],
        str(PROJECT_ROOT / project), f"{service} logs", head_tail=True
    )


@mcp.tool()
def docker_compose_build(project: str, service: str = "") -> str:
    """Build docker compose services. Optionally scope to one service."""
    cmd = ["docker", "compose", "build"] + ([service] if service else [])
    return run_safe(cmd, str(PROJECT_ROOT / project), "docker build", timeout=300)


@mcp.tool()
def docker_compose_restart(project: str, service: str = "") -> str:
    """Restart docker compose services. Optionally scope to one service."""
    cmd = ["docker", "compose", "restart"] + ([service] if service else [])
    return run_safe(cmd, str(PROJECT_ROOT / project), "docker restart")


@mcp.tool()
def deploy_local(project: str, service: str = "", run_tests_first: bool = False) -> str:
    """
    Full local deploy cycle: [tests →] build → up -d → ps.
    Sends Telegram notification on completion or test failure.
    Call this after write_file() to apply code changes.
    """
    path    = str(PROJECT_ROOT / project)
    results = []

    if run_tests_first:
        test_out = run_safe(["pytest", "--tb=short", "-q"], path, "pytest")
        results.append(f"=== Tests ===\n{test_out}")
        if "failed" in test_out or "error" in test_out.lower():
            _telegram_send(f"⚠️ *{project}* — deploy aborted, tests failed.\n```\n{test_out[:400]}\n```")
            return "\n".join(results) + "\n[Deploy aborted — fix failing tests first]"

    build_cmd = ["docker", "compose", "build"] + ([service] if service else [])
    results.append(f"=== Build ===\n{run_safe(build_cmd, path, 'build', timeout=300)}")

    up_cmd = ["docker", "compose", "up", "-d"] + (["--no-deps", service] if service else [])
    results.append(f"=== Up ===\n{run_safe(up_cmd, path, 'up', timeout=120)}")

    ps_out = run_safe(["docker", "compose", "ps"], path)
    results.append(f"=== Status ===\n{ps_out}")

    _telegram_send(f"🚀 *{project}* — local deploy complete.\n```\n{ps_out[:300]}\n```")
    return "\n".join(results)


@mcp.tool()
def audit_named_volumes(project: str) -> str:
    """
    Inspect docker-compose.yml for bind mounts that should be named volumes.
    Reports ./ or ../ volume entries that look like code directories.
    """
    compose_path = PROJECT_ROOT / project / "docker-compose.yml"
    if not compose_path.exists():
        return f"[docker-compose.yml not found in {project}]"
    content = compose_path.read_text()
    matches = re.findall(r'^\s+- (\.\.?/[^:"\s]+:[^"\s]+)', content, re.MULTILINE)
    if not matches:
        return "[No bind mounts found]"
    lines = [f"Found {len(matches)} bind mount(s) to review:"]
    for m in matches:
        lines.append(f"  {m}")
    lines += ["", "Convert code dirs to named volumes + Dockerfile COPY.",
              "Keep config file mounts as bind mounts."]
    return "\n".join(lines)


@mcp.tool()
def run_tests(project: str, test_command: str = "pytest") -> str:
    """Run tests. Allowed: pytest, npm test, npm run build"""
    allowed = {
        "pytest":        ["pytest", "--tb=short", "-q"],
        "npm test":      ["npm", "test"],
        "npm run build": ["npm", "run", "build"],
    }
    if test_command not in allowed:
        return f"[Blocked. Allowed: {', '.join(allowed.keys())}]"
    return run_safe(allowed[test_command], str(PROJECT_ROOT / project), f"{test_command} output")


# ─── Dev tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def tool_status() -> str:
    """Show which dev tools are installed. Call if a tool command fails."""
    checks = {
        "rg (ripgrep)":  "rg",
        "jq":            "jq",
        "black":         "black",
        "ruff":          "ruff",
        "pylint":        "pylint",
        "semgrep":       "semgrep",
        "http (httpie)": "http",
        "prettier":      "prettier",
        "eslint":        "eslint",
        "sg (ast-grep)": "sg",
    }
    lines = [f"{'✅' if _cmd_exists(cmd) else '❌'} {label}" for label, cmd in checks.items()]
    return "\n".join(lines)


@mcp.tool()
def tool_install(tool: str) -> str:
    """Install or reinstall a dev tool. Available: ripgrep, jq, black, ruff, pylint, semgrep, httpie, prettier, eslint, ast-grep"""
    apt  = {"ripgrep": "ripgrep", "jq": "jq"}
    pip  = {"black": "black", "ruff": "ruff", "pylint": "pylint",
             "semgrep": "semgrep", "httpie": "httpie"}
    npm  = {"prettier": "prettier", "eslint": "eslint"}
    t    = tool.lower().strip()
    if t in apt:   return _apt_install(apt[t])
    if t in pip:   return _pip_install(pip[t])
    if t in npm:   return _npm_global(npm[t])
    if t == "ast-grep":
        return (run_safe(["cargo", "install", "ast-grep", "--quiet"], label="cargo", timeout=300)
                if _cmd_exists("cargo") else _npm_global("@ast-grep/cli"))
    return f"[Unknown tool: {tool}]"


@mcp.tool()
def lint(project: str, file_path: str, linter: str = "auto") -> str:
    """
    Lint a file. linter=auto detects by extension (.py → ruff, .js/.ts → eslint).
    Run this after every write_file() call.
    """
    full_path = str(PROJECT_ROOT / project / file_path)
    ext       = Path(file_path).suffix.lower()
    if linter == "auto":
        linter = "ruff" if ext == ".py" else "eslint" if ext in (".js",".ts",".jsx",".tsx") else "ruff"
    cmds = {
        "ruff":    ["ruff", "check", full_path],
        "pylint":  ["pylint", "--output-format=text", full_path],
        "eslint":  ["eslint", "--format=compact", full_path],
        "semgrep": ["semgrep", "--config=auto", "--quiet", full_path],
    }
    if linter not in cmds:
        return f"[Unknown linter: {linter}]"
    return run_safe(cmds[linter], label=f"{linter} output", timeout=60)


@mcp.tool()
def lint_project(project: str, linter: str = "auto") -> str:
    """Lint entire project. auto runs ruff on Python and eslint on JS/TS."""
    path    = str(PROJECT_ROOT / project)
    results = []
    if linter in ("auto", "ruff") and _cmd_exists("ruff"):
        results.append(f"=== ruff ===\n{run_safe(['ruff', 'check', '.'], path, 'ruff', timeout=60)}")
    if linter in ("auto", "eslint") and _cmd_exists("eslint"):
        results.append(f"=== eslint ===\n{run_safe(['eslint','--format=compact','--ext','.js,.ts,.jsx,.tsx','.'], path, 'eslint', timeout=60)}")
    return "\n".join(results) or "[No linters ran — check tool_status()]"


@mcp.tool()
def format_file(project: str, file_path: str, formatter: str = "auto") -> str:
    """
    Format a file in place. auto detects by extension (.py → black, others → prettier).
    Cache is invalidated after formatting.
    """
    full_path = str(PROJECT_ROOT / project / file_path)
    ext       = Path(file_path).suffix.lower()
    if formatter == "auto":
        formatter = "black" if ext == ".py" else "prettier"
    cmds = {
        "black":    ["black", "--quiet", full_path],
        "prettier": ["prettier", "--write", full_path],
    }
    if formatter not in cmds:
        return f"[Unknown formatter: {formatter}]"
    result = run_safe(cmds[formatter], label=f"{formatter} output")
    cache_evict(project, file_path)
    return result + f"\n[Cache invalidated: {file_path}]"


@mcp.tool()
def analyse_code(project: str, file_path: str) -> str:
    """
    Full static analysis: lint + semgrep security scan.
    Run on auth, billing, payment, or any sensitive code before pushing to staging.
    """
    results = ["=== Lint ===", lint(project, file_path)]
    if _cmd_exists("semgrep"):
        full_path = str(PROJECT_ROOT / project / file_path)
        results += ["=== Security (semgrep) ===",
                    run_safe(["semgrep", "--config=auto", "--quiet", full_path], label="semgrep", timeout=120)]
    return "\n".join(results)


@mcp.tool()
def ast_search(project: str, pattern: str, language: str = "python") -> str:
    """
    Structural code search using ast-grep (sg).
    More precise than grep — finds code by structure not text.
    Examples:
      pattern="def $FUNC($$$):" language="python"    — all function defs
      pattern="console.log($$$)" language="javascript" — all console.log calls
    """
    if not _cmd_exists("sg"):
        return "[ast-grep not installed. Run tool_install('ast-grep')]"
    return run_safe(["sg", "run", "--pattern", pattern, "--lang", language, "."],
                    str(PROJECT_ROOT / project), "ast-grep", timeout=60)


@mcp.tool()
def http_request(method: str, url: str, headers: str = "", body: str = "") -> str:
    """
    Make an HTTP request using httpie to test API endpoints.
    Use after deploy_local() to verify changes work correctly.
    headers: space-separated "Key:Value" pairs
    body: JSON string for POST/PUT/PATCH
    """
    if not _cmd_exists("http"):
        return "[httpie not installed. Run tool_install('httpie')]"
    cmd = ["http", "--ignore-stdin", "--timeout=10", method.upper(), url]
    if headers:
        cmd += headers.split()
    if body:
        cmd += ["--raw", body]
    return run_safe(cmd, label="http response", timeout=15)


@mcp.tool()
def jq_query(project: str, file_path: str, query: str) -> str:
    """Run a jq query against a JSON file. Useful for docker inspect, config files, API responses."""
    if not _cmd_exists("jq"):
        return "[jq not installed. Run tool_install('jq')]"
    return run_safe(["jq", query, str(PROJECT_ROOT / project / file_path)], label="jq output")


# ─── Remote server registry ───────────────────────────────────────────────────

@mcp.tool()
def remote_add(project: str, host: str, user: str, ssh_key_path: str = "", port: int = 22) -> str:
    """
    Register a remote server for a project.
    Credentials stored once in remote_servers.json, reused by all remote_* tools.
    """
    remotes = load_remotes()
    remotes[project] = {
        "host": host, "user": user, "port": port,
        "ssh_key_path": ssh_key_path or str(Path.home() / ".ssh" / "id_rsa"),
        "added": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    save_remotes(remotes)
    return f"[Remote registered: {user}@{host}:{port} for {project}]"


@mcp.tool()
def remote_list() -> str:
    """List all registered remote servers."""
    remotes = load_remotes()
    if not remotes:
        return "[No remotes registered. Use remote_add() first.]"
    return "\n".join(f"{p}: {c['user']}@{c['host']}:{c['port']}" for p, c in remotes.items())


@mcp.tool()
def remote_remove(project: str) -> str:
    """Remove a registered remote server."""
    remotes = load_remotes()
    if project not in remotes:
        return f"[No remote for {project}]"
    del remotes[project]
    save_remotes(remotes)
    return f"[Remote removed: {project}]"


def _ssh(project: str, command: str, timeout: int = 60) -> str:
    remotes = load_remotes()
    if project not in remotes:
        return f"[No remote for {project}. Use remote_add() first.]"
    cfg = remotes[project]
    return run_safe([
        "ssh", "-i", cfg["ssh_key_path"], "-p", str(cfg["port"]),
        "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
        f"{cfg['user']}@{cfg['host']}", command,
    ], label=f"ssh:{project}", timeout=timeout)


@mcp.tool()
def remote_exec(project: str, command: str) -> str:
    """Run a shell command on the registered remote server for a project."""
    return _ssh(project, command)


@mcp.tool()
def remote_git_pull(project: str, remote_path: str, branch: str = "main") -> str:
    """Git pull on the remote server."""
    return _ssh(project,
        f"cd {remote_path} && git fetch origin && git checkout {branch} && git pull origin {branch}",
        timeout=60)


@mcp.tool()
def remote_rebuild(project: str, remote_path: str, service: str = "") -> str:
    """Docker compose build + up on remote. Sends Telegram notification."""
    svc   = service or ""
    build = _ssh(project, f"cd {remote_path} && docker compose build {svc}".strip(), timeout=300)
    up    = _ssh(project, f"cd {remote_path} && docker compose up -d {svc}".strip(), timeout=120)
    ps    = _ssh(project, f"cd {remote_path} && docker compose ps")
    _telegram_send(f"🚀 *{project}* — remote rebuild complete.\n```\n{ps[:400]}\n```")
    return f"=== Build ===\n{build}\n=== Up ===\n{up}\n=== Status ===\n{ps}"


@mcp.tool()
def remote_logs(project: str, remote_path: str, service: str, lines: int = 50) -> str:
    """Docker compose logs on remote server."""
    return _ssh(project, f"cd {remote_path} && docker compose logs --tail {min(lines,200)} {service}")


@mcp.tool()
def remote_deploy(project: str, remote_path: str, branch: str = "main", service: str = "") -> str:
    """Full remote deploy: git pull → rebuild → notify. Run after merging staging → main."""
    pull    = remote_git_pull(project, remote_path, branch)
    rebuild = remote_rebuild(project, remote_path, service)
    return f"=== Pull ===\n{pull}\n=== Rebuild ===\n{rebuild}"


# ─── Shared memory ────────────────────────────────────────────────────────────

@mcp.tool()
def memory_set(key: str, value: str) -> str:
    """
    Store a value in shared agent memory (persisted across sessions).
    Key patterns:
      project:<name>:summary  — project state
      project:<name>:issue    — current bug
      task:<slug>:result      — completed task output
    Always call this before finishing a task.
    """
    data = load_memory()
    data[key] = {"value": value, "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}
    save_memory(data)
    return f"[Stored: {key}]"


@mcp.tool()
def memory_get(key: str) -> str:
    """Retrieve a value from shared agent memory."""
    data = load_memory()
    if key not in data:
        return f"[Not found: {key}]"
    e = data[key]
    return f"[Updated: {e['updated']}]\n{e['value']}"


@mcp.tool()
def memory_list(prefix: str = "") -> str:
    """List all memory keys, optionally filtered by prefix."""
    data = load_memory()
    keys = [k for k in data if k.startswith(prefix)]
    if not keys:
        return "[No memory entries]"
    return "\n".join(f"{k}  ({data[k]['updated']})" for k in sorted(keys))


@mcp.tool()
def memory_delete(key: str) -> str:
    """Delete a key from shared memory."""
    data = load_memory()
    if key not in data:
        return f"[Not found: {key}]"
    del data[key]
    save_memory(data)
    return f"[Deleted: {key}]"


# ─── Agent router ─────────────────────────────────────────────────────────────

AGENT_COMMANDS = {
    "kimi":   ["kimi",   "--quiet", "--afk", "-p"],
    "gemini": ["gemini", "--"],
}

ROUTING_GUIDE = """
Agent routing (for Codex orchestration):
  kimi    — large file analysis, frontend/UI, visual tasks, wide codebase scans
  gemini  — web research, documentation, 1M+ token context tasks
  codex   — architecture, logic, code generation, debugging (default)

Efficient delegation workflow:
  1. task_start(project, task)          — load all context in one call
  2. memory_get(key)                    — load specific prior findings
  3. route_task(task, agent, key)       — delegate with context
  4. memory_set(key, result)            — store result for next agent
  5. telegram_notify(msg)               — report completion
"""


@mcp.tool()
def route_task(task: str, agent: str, context_key: str = "") -> str:
    """
    Delegate a task to Kimi or Gemini CLI.
    context_key: memory key prepended as context — prevents re-deriving state.
    Save results with memory_set() so subsequent agents inherit them.
    """
    if agent not in AGENT_COMMANDS:
        return f"[Unknown agent '{agent}']\n{ROUTING_GUIDE}"
    prompt = task
    if context_key:
        data = load_memory()
        if context_key in data:
            prompt = f"Context ({context_key}):\n{data[context_key]['value']}\n\n---\n\n{task}"
    return run_safe(AGENT_COMMANDS[agent] + [prompt], label=f"{agent} response", timeout=300)


@mcp.tool()
def routing_guide() -> str:
    """Return the agent routing and orchestration guide."""
    return ROUTING_GUIDE.strip()


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
