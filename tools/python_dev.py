from __future__ import annotations

from core.paths import UnsafePathError, safe_project_cwd
from core.permissions import PermissionDenied, check_permission
from core.runtime import cmd_exists, run_safe


def register(mcp) -> None:
    @mcp.tool()
    def python_import_fix(project: str, path_filter: str = '.', confirm: bool = False, dry_run: bool = False) -> str:
        try:
            check_permission('write', tool='python_import_fix', confirm=confirm)
            cwd = safe_project_cwd(project)
        except (PermissionDenied, UnsafePathError) as exc:
            return str(exc) if isinstance(exc, PermissionDenied) else f"[Unsafe path: {exc}]"
        commands = []
        if cmd_exists('autoflake'):
            commands.append(['autoflake', '--in-place', '--remove-all-unused-imports', '--recursive', path_filter])
        if cmd_exists('isort'):
            commands.append(['isort', path_filter])
        if dry_run:
            return '[Dry run]\n' + '\n'.join(' '.join(cmd) for cmd in commands)
        results = []
        if cmd_exists('autoflake'):
            results.append('=== autoflake ===\n' + run_safe(commands[0], cwd, 'autoflake', timeout=120))
        else:
            results.append('[autoflake not installed]')
        if cmd_exists('isort'):
            results.append('=== isort ===\n' + run_safe(commands[-1], cwd, 'isort', timeout=120))
        else:
            results.append('[isort not installed]')
        return '\n'.join(results)
