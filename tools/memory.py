from __future__ import annotations

from core.audit import audit_event
from core.memory_store import memory_delete as store_delete
from core.memory_store import memory_get as store_get
from core.memory_store import memory_list as store_list
from core.memory_store import memory_search as store_search
from core.memory_store import memory_set as store_set


def register(mcp) -> None:
    @mcp.tool()
    def memory_set(key: str, value: str, namespace: str = 'general', ttl_seconds: int = 0) -> str:
        store_set(namespace, key, value, ttl_seconds=ttl_seconds)
        audit_event('memory_set', namespace=namespace, key=key, ttl_seconds=ttl_seconds)
        return f"[Stored: {namespace}:{key}]"

    @mcp.tool()
    def memory_get(key: str, namespace: str = 'general') -> str:
        entry = store_get(namespace, key)
        if not entry:
            return f"[Not found: {namespace}:{key}]"
        return f"[Updated: {entry['updated']}]\n{entry['value']}"

    @mcp.tool()
    def memory_list(prefix: str = '', namespace: str = 'general') -> str:
        rows = store_list(namespace, prefix)
        if not rows:
            return '[No memory entries]'
        return '\n'.join(f"{key}  ({entry['updated']})" for key, entry in rows)

    @mcp.tool()
    def memory_delete(key: str, namespace: str = 'general') -> str:
        removed = store_delete(namespace, key)
        if not removed:
            return f"[Not found: {namespace}:{key}]"
        audit_event('memory_delete', namespace=namespace, key=key)
        return f"[Deleted: {namespace}:{key}]"

    @mcp.tool()
    def memory_search(query: str, namespace: str = 'general') -> str:
        rows = store_search(namespace, query)
        audit_event('memory_search', namespace=namespace, query=query, matches=len(rows))
        if not rows:
            return '[No memory matches]'
        return '\n\n'.join(f"{key}\n[Updated: {entry['updated']}]\n{entry['value']}" for key, entry in rows)
