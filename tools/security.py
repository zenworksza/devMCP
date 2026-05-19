from __future__ import annotations

from core.paths import UnsafePathError, safe_project_cwd
from core.runtime import cmd_exists, run_safe

SECRET_PATTERNS = (
    r'(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[\'\"][^\'\"]{12,}',
    r'AKIA[0-9A-Z]{16}',
    r'ghp_[A-Za-z0-9_]{30,}',
    r'-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----',
)


def register(mcp) -> None:
    @mcp.tool()
    def secret_scan(project: str, path_filter: str = '.') -> str:
        try:
            cwd = safe_project_cwd(project)
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"
        if not cmd_exists('rg'):
            return '[rg not installed]'
        results = []
        for pattern in SECRET_PATTERNS:
            out = run_safe(['rg', '--line-number', '--hidden', '--glob', '!.git', pattern, path_filter], cwd, f'secret pattern {pattern}', head_tail=True)
            if out.strip() and '[Command not found:' not in out:
                results.append(f"=== Pattern ===\n{pattern}\n{out}")
        return '\n\n'.join(results) if results else '[No obvious secrets found]'
