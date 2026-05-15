from __future__ import annotations

import time

from core.runtime import load_memory, save_memory


def register(mcp) -> None:
    @mcp.tool()
    def memory_set(key: str, value: str) -> str:
        """
        Store a value in shared agent memory (persisted across sessions).
        Key patterns:
          project:<name>:summary  - project state
          project:<name>:issue    - current bug
          task:<slug>:result      - completed task output
        """
        data = load_memory()
        data[key] = {"value": value, "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}
        save_memory(data)
        return f"[Stored: {key}]"

    @mcp.tool()
    def memory_get(key: str) -> str:
        """Retrieve a value from shared agent memory."""
        data = load_memory()
        if key not in data:
            return f"[Not found: {key}]"
        entry = data[key]
        return f"[Updated: {entry['updated']}]\n{entry['value']}"

    @mcp.tool()
    def memory_list(prefix: str = "") -> str:
        """List all memory keys, optionally filtered by prefix."""
        data = load_memory()
        keys = [k for k in data if k.startswith(prefix)]
        if not keys:
            return "[No memory entries]"
        return "\n".join(f"{k}  ({data[k]['updated']})" for k in sorted(keys))

    @mcp.tool()
    def memory_delete(key: str) -> str:
        """Delete a key from shared memory."""
        data = load_memory()
        if key not in data:
            return f"[Not found: {key}]"
        del data[key]
        save_memory(data)
        return f"[Deleted: {key}]"
