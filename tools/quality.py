from __future__ import annotations

from pathlib import Path

from core.paths import UnsafePathError, safe_project_cwd, safe_project_file
from core.permissions import PermissionDenied, check_permission
from core.runtime import apt_install, cmd_exists, npm_global, pip_install, run_safe
from tools.files import cache_evict


def register(mcp) -> None:
    @mcp.tool()
    def run_tests(project: str, test_command: str = 'pytest') -> str:
        allowed = {
            'pytest': ['pytest', '--tb=short', '-q'],
            'npm test': ['npm', 'test'],
            'npm run build': ['npm', 'run', 'build'],
        }
        if test_command not in allowed:
            return f"[Blocked. Allowed: {', '.join(allowed.keys())}]"
        try:
            return run_safe(allowed[test_command], safe_project_cwd(project), f'{test_command} output')
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"

    @mcp.tool()
    def tool_status() -> str:
        checks = {'rg (ripgrep)': 'rg', 'jq': 'jq', 'black': 'black', 'ruff': 'ruff', 'eslint': 'eslint', 'prettier': 'prettier', 'semgrep': 'semgrep', 'http (httpie)': 'http'}
        return '\n'.join(f"{'OK' if cmd_exists(cmd) else 'MISSING'} {label}" for label, cmd in checks.items())

    @mcp.tool()
    def tool_install(tool: str, confirm: bool = False) -> str:
        try:
            check_permission('install', tool='tool_install', confirm=confirm)
        except PermissionDenied as exc:
            return str(exc)
        apt = {'ripgrep': 'ripgrep', 'jq': 'jq'}
        pip = {'black': 'black', 'ruff': 'ruff', 'pylint': 'pylint', 'semgrep': 'semgrep', 'httpie': 'httpie'}
        npm = {'prettier': 'prettier', 'eslint': 'eslint'}
        target = tool.lower().strip()
        if target in apt:
            return apt_install(apt[target])
        if target in pip:
            return pip_install(pip[target])
        if target in npm:
            return npm_global(npm[target])
        return f"[Unknown tool: {tool}]"
