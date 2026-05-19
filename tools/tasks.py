from __future__ import annotations

from core.audit import audit_event
from core.tasks import task_create as store_create
from core.tasks import task_get as store_get
from core.tasks import task_list as store_list
from core.tasks import task_update as store_update


def register(mcp) -> None:
    @mcp.tool()
    def task_create(title: str, prompt: str, project: str = '', agent: str = '', namespace: str = 'general') -> str:
        task_id = store_create(title, prompt, project=project, agent=agent, namespace=namespace)
        audit_event('task_create', task_id=task_id, project=project, agent=agent, namespace=namespace)
        return task_id

    @mcp.tool()
    def task_list(status: str = '') -> str:
        rows = store_list(status)
        if not rows:
            return '[No tasks]'
        return '\n'.join(f"{row['id']}  {row['status']}  {row['title']}" for row in rows)

    @mcp.tool()
    def task_get(task_id: str) -> str:
        row = store_get(task_id)
        if not row:
            return f"[Task not found: {task_id}]"
        return '\n'.join(f"{key}: {value}" for key, value in row.items())

    @mcp.tool()
    def task_complete(task_id: str, result: str) -> str:
        ok = store_update(task_id, 'complete', result)
        audit_event('task_complete', task_id=task_id, ok=ok)
        return '[Task completed]' if ok else f"[Task not found: {task_id}]"

    @mcp.tool()
    def task_fail(task_id: str, result: str) -> str:
        ok = store_update(task_id, 'failed', result)
        audit_event('task_fail', task_id=task_id, ok=ok)
        return '[Task failed]' if ok else f"[Task not found: {task_id}]"
