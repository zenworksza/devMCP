from __future__ import annotations

import os

from core.paths import UnsafePathError, safe_project_cwd, safe_project_file
from core.runtime import cmd_exists, run_safe


def _database_url(project: str, database_url: str = '') -> str:
    if database_url:
        return database_url
    try:
        env_path = safe_project_file(project, '.env', allow_sensitive=True)
    except UnsafePathError:
        env_path = None
    if env_path and env_path.exists():
        for line in env_path.read_text(errors='replace').splitlines():
            if line.startswith('DATABASE_URL='):
                return line.split('=', 1)[1].strip().strip('"\'')
    return os.environ.get('DATABASE_URL', '')


def _readonly_sql(query: str) -> bool:
    return query.strip().lower().startswith(('select', 'with', 'show', 'explain'))


def register(mcp) -> None:
    @mcp.tool()
    def db_readonly_query(project: str, query: str, database_url: str = '') -> str:
        if not _readonly_sql(query):
            return '[Blocked: db_readonly_query only allows SELECT, WITH, SHOW, or EXPLAIN.]'
        url = _database_url(project, database_url)
        if not url:
            return '[No database URL provided or found in .env]'
        if not cmd_exists('psql'):
            return '[psql not installed]'
        try:
            return run_safe(['psql', url, '-c', query], safe_project_cwd(project), 'psql output', timeout=60, head_tail=True)
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"
