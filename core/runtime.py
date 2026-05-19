from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path.home() / 'workspaces'
SERVER_DIR = Path.home() / 'mcp-dev-server'
MEMORY_FILE = SERVER_DIR / 'memory.json'
REMOTE_FILE = SERVER_DIR / 'remote_servers.json'
CACHE_FILE = SERVER_DIR / 'file_cache.json'
TOOLS_FILE = SERVER_DIR / 'tools_installed.json'
AGENTS_MD = SERVER_DIR / 'AGENTS.md'
PROJECT_PATHS_FILE = SERVER_DIR / 'project_paths.json'
CONFIG_FILE = SERVER_DIR / 'config.json'

MAX_OUTPUT = 4000
MAX_LINES_FULL = 200
HEAD_LINES = 20
TAIL_LINES = 10

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
DEFAULT_CONFIG = {
    'allow_raw_remote_shell': False,
    'allow_telegram_codex_fallback': False,
    'allow_codex_dangerous_bypass': False,
}

SERVER_DIR.mkdir(parents=True, exist_ok=True)


def resolve_project_path(project: str) -> Path:
    if PROJECT_PATHS_FILE.exists():
        try:
            mapping = json.loads(PROJECT_PATHS_FILE.read_text(encoding='utf-8'))
            override = mapping.get(project)
            if override:
                return Path(override).expanduser()
        except (json.JSONDecodeError, TypeError):
            pass
    return PROJECT_ROOT / project


def trim(text: str, label: str = 'output', head_tail: bool = False) -> str:
    from core.security import redact_text

    text = redact_text(text)
    if len(text) <= MAX_OUTPUT:
        return text

    lines = text.splitlines()
    if head_tail and len(lines) > HEAD_LINES + TAIL_LINES:
        head = '\n'.join(lines[:HEAD_LINES])
        tail = '\n'.join(lines[-TAIL_LINES:])
        omitted = len(lines) - HEAD_LINES - TAIL_LINES
        return (
            f"{head}\n\n"
            f"[... {omitted} lines omitted - use read_file(start_line, end_line) "
            f"or search_files() to access specific sections ...]\n\n"
            f"{tail}"
        )

    kept = text[:MAX_OUTPUT]
    lines_cut = text[MAX_OUTPUT:].count('\n')
    return kept + f"\n\n[{label} trimmed - {lines_cut} more lines not shown. Use line ranges to narrow scope.]"


def tool_env() -> dict[str, str]:
    env = os.environ.copy()
    env['PATH'] = (
        f"{SERVER_DIR / '.venv' / 'bin'}:"
        '/home/mdb/.local/bin:'
        '/home/mdb/.cargo/bin:'
        '/home/mdb/.npm-global/bin:'
        '/usr/local/bin:/usr/bin:/bin:'
        + env.get('PATH', '')
    )
    return env


def run_safe(
    cmd: list[str],
    cwd: str | None = None,
    label: str = 'output',
    timeout: int = 60,
    head_tail: bool = False,
) -> str:
    from core.audit import audit_event, new_run_id
    from core.security import redact_text

    run_id = new_run_id()
    started = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=tool_env(),
        )
        combined = redact_text((result.stdout or '') + (result.stderr or ''))
        audit_event(
            'command_run',
            run_id=run_id,
            command=cmd,
            cwd=cwd or str(PROJECT_ROOT),
            label=label,
            status='ok' if result.returncode == 0 else 'error',
            returncode=result.returncode,
            duration_ms=int((time.time() - started) * 1000),
            output_preview=combined[:1000],
        )
        return trim(combined, label, head_tail=head_tail)
    except subprocess.TimeoutExpired:
        message = f"[Timed out after {timeout}s: {' '.join(cmd)}]"
        audit_event(
            'command_run',
            run_id=run_id,
            command=cmd,
            cwd=cwd or str(PROJECT_ROOT),
            label=label,
            status='timeout',
            duration_ms=int((time.time() - started) * 1000),
            output_preview=message[:1000],
        )
        return message
    except FileNotFoundError:
        message = f"[Command not found: {cmd[0]}]"
        audit_event(
            'command_run',
            run_id=run_id,
            command=cmd,
            cwd=cwd or str(PROJECT_ROOT),
            label=label,
            status='missing',
            duration_ms=int((time.time() - started) * 1000),
            output_preview=message[:1000],
        )
        return message
    except Exception as exc:
        message = f"[Error running command: {exc}]"
        audit_event(
            'command_run',
            run_id=run_id,
            command=cmd,
            cwd=cwd or str(PROJECT_ROOT),
            label=label,
            status='exception',
            duration_ms=int((time.time() - started) * 1000),
            output_preview=message[:1000],
        )
        return message


def load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            return {}
    return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def load_memory() -> dict:
    from core.memory_store import memory_list

    return {key: entry for key, entry in memory_list('general')}


def save_memory(data: dict) -> None:
    from core.memory_store import memory_delete, memory_list, memory_set

    for key, _ in memory_list('general'):
        memory_delete('general', key)
    for key, entry in data.items():
        if isinstance(entry, dict):
            memory_set('general', key, str(entry.get('value', '')))
        else:
            memory_set('general', key, str(entry))


def load_remotes() -> dict:
    return load_json(REMOTE_FILE)


def save_remotes(data: dict) -> None:
    save_json(REMOTE_FILE, data)


def load_cache() -> dict:
    return load_json(CACHE_FILE)


def save_cache(data: dict) -> None:
    save_json(CACHE_FILE, data)


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        save_json(CONFIG_FILE, DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    loaded = load_json(CONFIG_FILE)
    config = dict(DEFAULT_CONFIG)
    config.update({k: bool(v) for k, v in loaded.items() if k in DEFAULT_CONFIG})
    if config != loaded:
        save_json(CONFIG_FILE, config)
    return config


def cmd_exists(cmd: str) -> bool:
    try:
        subprocess.run(['which', cmd], capture_output=True, check=True, env=tool_env())
        return True
    except subprocess.CalledProcessError:
        return False


def pip_install(*packages: str) -> str:
    venv_pip = SERVER_DIR / '.venv' / 'bin' / 'pip'
    pip_cmd = str(venv_pip) if venv_pip.exists() else 'pip3'
    return run_safe([pip_cmd, 'install', '--quiet', *packages], label='pip', timeout=120)


def npm_global(*packages: str) -> str:
    return run_safe(['npm', 'install', '-g', '--quiet', *packages], label='npm', timeout=120)


def apt_install(*packages: str) -> str:
    return run_safe(['sudo', 'apt-get', 'install', '-y', '-qq', *packages], label='apt', timeout=120)


def ensure_tools() -> None:
    from core.permissions import PermissionDenied, check_permission

    installed = load_json(TOOLS_FILE)
    changed = False
    auto_install = os.environ.get('DEVMCP_AUTO_INSTALL', '0') == '1'

    def mark(tool: str, status: str) -> None:
        nonlocal changed
        installed[tool] = {'status': status, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}
        changed = True

    def install_or_mark(missing_name: str, installer) -> None:
        if not auto_install:
            mark(missing_name, 'missing')
            return
        try:
            check_permission('install', tool='ensure_tools', confirm=True)
        except PermissionDenied:
            mark(missing_name, 'missing')
            return
        installer()
        mark(missing_name, 'installed')

    if not cmd_exists('rg'):
        install_or_mark('ripgrep', lambda: apt_install('ripgrep'))
    if not cmd_exists('jq'):
        install_or_mark('jq', lambda: apt_install('jq'))
    for pkg, cmd in [
        ('black', 'black'),
        ('ruff', 'ruff'),
        ('pylint', 'pylint'),
        ('semgrep', 'semgrep'),
        ('httpie', 'http'),
    ]:
        if not cmd_exists(cmd):
            install_or_mark(pkg, lambda package=pkg: pip_install(package))
    for pkg, cmd in [('prettier', 'prettier'), ('eslint', 'eslint')]:
        if not cmd_exists(cmd):
            install_or_mark(pkg, lambda package=pkg: npm_global(package))
    if not cmd_exists('sg'):
        def _install_ast_grep() -> None:
            if cmd_exists('cargo'):
                run_safe(['cargo', 'install', 'ast-grep', '--quiet'], label='cargo', timeout=300)
            else:
                npm_global('@ast-grep/cli')
        install_or_mark('ast-grep', _install_ast_grep)

    if changed:
        save_json(TOOLS_FILE, installed)


def telegram_send(message: str) -> str:
    from core.audit import audit_event
    from core.security import redact_text

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return '[Telegram not configured]'
    safe_message = redact_text(message)
    params = urllib.parse.urlencode({'chat_id': TELEGRAM_CHAT_ID, 'text': safe_message}).encode()
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        with urllib.request.urlopen(url, data=params, timeout=15) as response:
            response.read()
        audit_event('telegram_send', status='sent', preview=safe_message[:300])
        return '[Telegram sent]'
    except Exception as exc:
        audit_event('telegram_send', status='error', preview=safe_message[:300], error=str(exc))
        return f'[Telegram error: {exc}]'
