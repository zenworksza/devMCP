from __future__ import annotations

from core.paths import UnsafePathError, safe_project_file
from core.permissions import PermissionDenied, check_permission
from core.runtime import cmd_exists, run_safe


def register(mcp) -> None:
    @mcp.tool()
    def http_request(method: str, url: str, headers: str = '', body: str = '') -> str:
        try:
            check_permission('network', tool='http_request', confirm=True)
        except PermissionDenied as exc:
            return str(exc)
        if not cmd_exists('http'):
            return "[httpie not installed. Run tool_install('httpie')]"
        cmd = ['http', '--ignore-stdin', '--timeout=10', method.upper(), url]
        if headers:
            cmd += headers.split()
        if body:
            cmd += ['--raw', body]
        return run_safe(cmd, label='http response', timeout=15)

    @mcp.tool()
    def jq_query(project: str, file_path: str, query: str) -> str:
        if not cmd_exists('jq'):
            return "[jq not installed. Run tool_install('jq')]"
        try:
            target = safe_project_file(project, file_path, must_exist=True, allow_sensitive=True)
        except UnsafePathError as exc:
            return f'[Unsafe path: {exc}]'
        return run_safe(['jq', query, str(target)], label='jq output')
