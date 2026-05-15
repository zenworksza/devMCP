from __future__ import annotations

from core.runtime import PROJECT_ROOT, run_safe
from tools.files import read_project_file


def register(mcp) -> None:
    @mcp.tool()
    def alembic_workflow(project: str, message: str) -> str:
        """
        Full Alembic migration cycle:
        1. Generate migration with autogenerate
        2. Show the generated file for review
        3. Run upgrade head
        """
        path = str(PROJECT_ROOT / project)
        gen = run_safe(["alembic", "revision", "--autogenerate", "-m", message], path, "alembic generate", timeout=120)
        versions = run_safe(["ls", "-t", "alembic/versions/"], path, "alembic versions")
        new_file = versions.splitlines()[0] if versions.splitlines() else ""
        content = read_project_file(project, f"alembic/versions/{new_file}") if new_file else "[No migration file found]"
        upgrade = run_safe(["alembic", "upgrade", "head"], path, "alembic upgrade", timeout=120)
        return f"=== Generated ===\n{gen}\n\n=== Migration File ===\n{content}\n\n=== Upgrade ===\n{upgrade}"
