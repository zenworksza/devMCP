from __future__ import annotations

from pathlib import Path

from core.runtime import SERVER_DIR


def _safe_module_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip().lower())
    return cleaned.strip("_")


def register(mcp) -> None:
    @mcp.tool()
    def mcp_tool_scaffold(module_name: str, tool_name: str) -> str:
        """Create a new tools/<module>.py file with a register(mcp) skeleton."""
        module = _safe_module_name(module_name)
        tool = _safe_module_name(tool_name)
        if not module or not tool:
            return "[module_name and tool_name are required]"
        path = SERVER_DIR / "tools" / f"{module}.py"
        if path.exists():
            return f"[File already exists: {path}]"
        content = f'''from __future__ import annotations


def register(mcp) -> None:
    @mcp.tool()
    def {tool}(project: str) -> str:
        """Describe what this tool does."""
        return "[Not implemented]"
'''
        path.write_text(content)
        return f"[Created: {path}]\nAdd 'tools.{module}' to registry.py MODULES."

    @mcp.tool()
    def mcp_skill_scaffold(module_name: str, skill_name: str) -> str:
        """Create a new skills/<module>.py file with a workflow skeleton."""
        module = _safe_module_name(module_name)
        skill = _safe_module_name(skill_name)
        if not module or not skill:
            return "[module_name and skill_name are required]"
        path = SERVER_DIR / "skills" / f"{module}.py"
        if path.exists():
            return f"[File already exists: {path}]"
        content = f'''from __future__ import annotations


def register(mcp) -> None:
    @mcp.tool()
    def {skill}(project: str) -> str:
        """Describe the workflow this skill performs."""
        steps = []
        return "\\n\\n".join(steps) if steps else "[Not implemented]"
'''
        path.write_text(content)
        return f"[Created: {path}]\nAdd 'skills.{module}' to registry.py MODULES."

    @mcp.tool()
    def new_project_note(project_name: str, stack: str = "", notes: str = "") -> str:
        """Create a Project.md note under ~/workspaces/<project> if it does not exist."""
        project = _safe_module_name(project_name)
        if not project:
            return "[project_name is required]"
        path = Path.home() / "workspaces" / project / "Project.md"
        if path.exists():
            return f"[File already exists: {path}]"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {project_name}\n\n## Stack\n{stack or 'TBD'}\n\n## Notes\n{notes or 'TBD'}\n")
        return f"[Created: {path}]"
