from __future__ import annotations

import os
import time

from core.runtime import PROJECT_ROOT, cmd_exists, run_safe


def _database_url(project: str, database_url: str = "") -> str:
    if database_url:
        return database_url
    env_path = PROJECT_ROOT / project / ".env"
    if env_path.exists():
        for line in env_path.read_text(errors="replace").splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return os.environ.get("DATABASE_URL", "")


def _readonly_sql(query: str) -> bool:
    stripped = query.strip().lower()
    return stripped.startswith(("select", "with", "show", "explain"))


def register(mcp) -> None:
    @mcp.tool()
    def db_readonly_query(project: str, query: str, database_url: str = "") -> str:
        """Run a read-only PostgreSQL query using psql."""
        if not _readonly_sql(query):
            return "[Blocked: db_readonly_query only allows SELECT, WITH, SHOW, or EXPLAIN.]"
        url = _database_url(project, database_url)
        if not url:
            return "[No database URL provided or found in .env]"
        if not cmd_exists("psql"):
            return "[psql not installed]"
        return run_safe(["psql", url, "-c", query], str(PROJECT_ROOT / project), "psql output", timeout=60, head_tail=True)

    @mcp.tool()
    def pg_dump_backup(project: str, database_url: str = "", output_dir: str = "backups") -> str:
        """Create a timestamped PostgreSQL dump under the project directory."""
        url = _database_url(project, database_url)
        if not url:
            return "[No database URL provided or found in .env]"
        if not cmd_exists("pg_dump"):
            return "[pg_dump not installed]"
        backup_dir = PROJECT_ROOT / project / output_dir
        backup_dir.mkdir(parents=True, exist_ok=True)
        output = backup_dir / f"db-{time.strftime('%Y%m%d-%H%M%S')}.dump"
        result = run_safe(["pg_dump", url, "-Fc", "-f", str(output)], str(PROJECT_ROOT / project), "pg_dump", timeout=300)
        return f"{result}\n[Backup path: {output}]"

    @mcp.tool()
    def pg_restore_backup(project: str, backup_file: str, database_url: str = "") -> str:
        """Restore a PostgreSQL custom-format dump with pg_restore."""
        url = _database_url(project, database_url)
        if not url:
            return "[No database URL provided or found in .env]"
        if not cmd_exists("pg_restore"):
            return "[pg_restore not installed]"
        return run_safe(["pg_restore", "--clean", "--if-exists", "-d", url, backup_file], str(PROJECT_ROOT / project), "pg_restore", timeout=300, head_tail=True)

    @mcp.tool()
    def sqlite_query(project: str, db_path: str, query: str) -> str:
        """Run a read-only SQLite query."""
        if not _readonly_sql(query):
            return "[Blocked: sqlite_query only allows SELECT, WITH, SHOW, or EXPLAIN.]"
        if not cmd_exists("sqlite3"):
            return "[sqlite3 not installed]"
        return run_safe(["sqlite3", "-header", "-column", db_path, query], str(PROJECT_ROOT / project), "sqlite output", head_tail=True)

    @mcp.tool()
    def redis_ping(host: str = "localhost", port: int = 6379) -> str:
        """Ping a Redis instance."""
        if not cmd_exists("redis-cli"):
            return "[redis-cli not installed]"
        return run_safe(["redis-cli", "-h", host, "-p", str(port), "PING"], label="redis output")

    @mcp.tool()
    def csv_summary(project: str, file_path: str) -> str:
        """Summarize CSV columns with csvstat."""
        if not cmd_exists("csvstat"):
            return "[csvkit not installed]"
        return run_safe(["csvstat", file_path], str(PROJECT_ROOT / project), "csvstat output", head_tail=True)
