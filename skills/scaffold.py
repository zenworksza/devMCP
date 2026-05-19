from __future__ import annotations

from pathlib import Path

from core.paths import safe_new_project_name
from core.permissions import PermissionDenied, check_permission
from core.runtime import SERVER_DIR


def _safe_module_name(name: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() or ch == '_' else '_' for ch in name.strip().lower())
    return cleaned.strip('_')


def register(mcp) -> None:
    @mcp.tool()
    def mcp_tool_scaffold(module_name: str, tool_name: str, confirm: bool = False, dry_run: bool = False) -> str:
        try:
            check_permission('write', tool='mcp_tool_scaffold', confirm=confirm)
        except PermissionDenied as exc:
            return str(exc)
        module = _safe_module_name(module_name)
        tool = _safe_module_name(tool_name)
        if not module or not tool:
            return '[module_name and tool_name are required]'
        path = SERVER_DIR / 'tools' / f'{module}.py'
        if path.exists():
            return f'[File already exists: {path}]'
        content = f"from __future__ import annotations\n\n\ndef register(mcp) -> None:\n    @mcp.tool()\n    def {tool}(project: str) -> str:\n        \"\"\"Describe what this tool does.\"\"\"\n        return \"[Not implemented]\"\n"
        if dry_run:
            return f'[Dry run] Would create: {path}'
        path.write_text(content, encoding='utf-8')
        return f"[Created: {path}]\nAdd 'tools.{module}' to registry.py MODULES."
