from __future__ import annotations

import json

from core.paths import UnsafePathError, safe_project_cwd, safe_project_file
from core.runtime import run_safe


def _section(name: str, body: str) -> str:
    return f'=== {name} ===\n{body}'


def _package_json_scripts(project: str) -> dict:
    try:
        path = safe_project_file(project, 'package.json', must_exist=True, allow_sensitive=True)
    except UnsafePathError:
        return {}
    try:
        return json.loads(path.read_text()).get('scripts', {})
    except Exception:
        return {}


def register(mcp) -> None:
    @mcp.tool()
    def ci_debug_workflow(project: str) -> str:
        try:
            path = safe_project_cwd(project)
        except UnsafePathError as exc:
            return f'[Unsafe path: {exc}]'
        scripts = _package_json_scripts(project)
        parts = [_section('Git', run_safe(['git', 'status', '--short'], path, 'git status'))]
        if 'lint' in scripts:
            parts.append(_section('npm lint', run_safe(['npm', 'run', 'lint'], path, 'npm lint', timeout=120, head_tail=True)))
        parts.append(_section('pytest', run_safe(['pytest', '--tb=short', '-q'], path, 'pytest', timeout=120, head_tail=True)))
        if 'build' in scripts:
            parts.append(_section('npm build', run_safe(['npm', 'run', 'build'], path, 'npm build', timeout=180, head_tail=True)))
        return '\n\n'.join(parts)
