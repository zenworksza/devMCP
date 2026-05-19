from __future__ import annotations

from core.memory_store import memory_list
from core.runtime import AGENTS_MD, resolve_project_path, telegram_send


def register(mcp) -> None:
    @mcp.tool()
    def telegram_notify(message: str) -> str:
        return telegram_send(message)

    @mcp.tool()
    def task_start(project: str, task_description: str) -> str:
        sections = []
        if AGENTS_MD.exists():
            sections.append(f"=== Operating Manual (AGENTS.md) ===\n{AGENTS_MD.read_text(encoding='utf-8')[:3000]}")
        found_project_md = False
        for name in ('Project.md', 'PROJECT.md', 'project.md'):
            path = resolve_project_path(project) / name
            if path.exists():
                sections.append(f"=== Project Context ({name}) ===\n{path.read_text(encoding='utf-8')[:3000]}")
                found_project_md = True
                break
        if not found_project_md:
            sections.append(
                f"[No Project.md found in {project}]\nCreate ~/workspaces/{project}/Project.md with stack, rules, key files, and remote info."
            )
        relevant = [(k, v) for k, v in memory_list('general') if project.lower() in k.lower()][:10]
        if relevant:
            sections.append('=== Prior Agent Work ===')
            for key, entry in relevant:
                sections.append(f"{key} (updated {entry['updated']}):\n{entry['value'][:400]}")
        else:
            sections.append('[No prior memory for this project - this may be a fresh task]')
        sections.append(f"=== Your Task ===\n{task_description}")
        sections.append(
            '=== Token Efficiency Rules ===\n'
            '1. Use file_outline() before read_file() - get structure first\n'
            '2. Use search_files() to locate code - never read whole dirs\n'
            '3. Use read_file(start_line, end_line) - never read >200 lines at once\n'
            '4. Save findings with memory_set() before finishing\n'
            '5. Use telegram_notify() to report completion'
        )
        return '\n\n'.join(sections)

    @mcp.tool()
    def project_context(project: str) -> str:
        for name in ('Project.md', 'PROJECT.md', 'project.md'):
            path = resolve_project_path(project) / name
            if path.exists():
                return path.read_text(encoding='utf-8')
        return f"[No Project.md found in {project}]\nCreate ~/workspaces/{project}/Project.md to give agents project context."
