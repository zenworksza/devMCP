from __future__ import annotations

from core.paths import UnsafePathError, safe_project_cwd
from core.runtime import run_safe


def _section(name: str, body: str) -> str:
    return f'=== {name} ===\n{body}'


def register(mcp) -> None:
    @mcp.tool()
    def project_health_check(project: str) -> str:
        try:
            path = safe_project_cwd(project)
        except UnsafePathError as exc:
            return f'[Unsafe path: {exc}]'
        parts = [
            _section('Git', run_safe(['git', 'status', '--short'], path, 'git status')),
            _section('Code Size', run_safe(['tokei', '.'], path, 'tokei', head_tail=True)),
            _section('Python Lint', run_safe(['ruff', 'check', '.'], path, 'ruff', timeout=60, head_tail=True)),
            _section('Docker', run_safe(['docker', 'compose', 'ps'], path, 'docker ps')),
        ]
        return '\n\n'.join(parts)
