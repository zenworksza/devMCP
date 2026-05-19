from __future__ import annotations

from core.paths import UnsafePathError, safe_project_cwd
from core.permissions import PermissionDenied, check_permission
from core.runtime import cmd_exists, run_safe


def register(mcp) -> None:
    @mcp.tool()
    def js_dependency_graph(project: str, path_filter: str = '.') -> str:
        try:
            cwd = safe_project_cwd(project)
        except UnsafePathError as exc:
            return f'[Unsafe path: {exc}]'
        if not cmd_exists('madge'):
            return '[madge not installed]'
        return run_safe(['madge', '--summary', path_filter], cwd, 'madge output', timeout=120)

    @mcp.tool()
    def js_circular_deps(project: str, path_filter: str = '.') -> str:
        try:
            cwd = safe_project_cwd(project)
        except UnsafePathError as exc:
            return f'[Unsafe path: {exc}]'
        if not cmd_exists('madge'):
            return '[madge not installed]'
        return run_safe(['madge', '--circular', path_filter], cwd, 'madge output', timeout=120)

    @mcp.tool()
    def js_find_unused_exports(project: str) -> str:
        try:
            cwd = safe_project_cwd(project)
        except UnsafePathError as exc:
            return f'[Unsafe path: {exc}]'
        if not cmd_exists('ts-prune'):
            return '[ts-prune not installed]'
        return run_safe(['ts-prune'], cwd, 'ts-prune output', timeout=120, head_tail=True)
