from __future__ import annotations

from core.runtime import AGENTS_MD, PROJECT_ROOT, load_memory, telegram_send


def register(mcp) -> None:
    @mcp.tool()
    def telegram_notify(message: str) -> str:
        """
        Send a Telegram message to the developer.
        Use to report task completion, errors, or to request approval.
        Include project name and what action is needed.
        """
        return telegram_send(message)

    @mcp.tool()
    def task_start(project: str, task_description: str) -> str:
        """
        CALL THIS FIRST before any task. Returns all context needed to work efficiently:
          - Project.md (stack, rules, key files, remote server)
          - Prior agent memory for this project
          - Reminder of token efficiency rules
        """
        sections = []
        if AGENTS_MD.exists():
            sections.append(f"=== Operating Manual (AGENTS.md) ===\n{AGENTS_MD.read_text()[:3000]}")

        found_project_md = False
        for name in ("Project.md", "PROJECT.md", "project.md"):
            path = PROJECT_ROOT / project / name
            if path.exists():
                sections.append(f"=== Project Context ({name}) ===\n{path.read_text()[:3000]}")
                found_project_md = True
                break
        if not found_project_md:
            sections.append(
                f"[No Project.md found in {project}]\n"
                f"Create ~/workspaces/{project}/Project.md with stack, rules, key files, and remote info."
            )

        data = load_memory()
        relevant = {k: v for k, v in data.items() if project.lower() in k.lower()}
        if relevant:
            sections.append("=== Prior Agent Work ===")
            for k, v in list(relevant.items())[:10]:
                sections.append(f"{k} (updated {v['updated']}):\n{v['value'][:400]}")
        else:
            sections.append("[No prior memory for this project - this may be a fresh task]")

        sections.append(f"=== Your Task ===\n{task_description}")
        sections.append(
            "=== Token Efficiency Rules ===\n"
            "1. Use file_outline() before read_file() - get structure first\n"
            "2. Use search_files() to locate code - never read whole dirs\n"
            "3. Use read_file(start_line, end_line) - never read >200 lines at once\n"
            "4. Save findings with memory_set() before finishing\n"
            "5. Use telegram_notify() to report completion"
        )

        return "\n\n".join(sections)

    @mcp.tool()
    def project_context(project: str) -> str:
        """
        Load Project.md for a project.
        Prefer task_start() which loads this plus memory in one call.
        """
        for name in ("Project.md", "PROJECT.md", "project.md"):
            path = PROJECT_ROOT / project / name
            if path.exists():
                return path.read_text()
        return (
            f"[No Project.md found in {project}]\n"
            f"Create ~/workspaces/{project}/Project.md to give agents project context."
        )
