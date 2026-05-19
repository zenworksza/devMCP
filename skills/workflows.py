from __future__ import annotations

from core.permissions import PermissionDenied, check_permission
from core.workflow_runner import list_workflows, run_workflow


def register(mcp) -> None:
    @mcp.tool()
    def workflow_list() -> str:
        return '\n'.join(list_workflows())

    @mcp.tool()
    def workflow_run(name: str, project: str, dry_run: bool = True, confirm: bool = False) -> str:
        try:
            if not dry_run:
                check_permission('deploy', tool='workflow_run', confirm=confirm)
        except PermissionDenied as exc:
            return str(exc)
        return run_workflow(name, project, dry_run=dry_run, confirm=confirm)
