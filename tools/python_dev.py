from __future__ import annotations

from core.runtime import PROJECT_ROOT, cmd_exists, run_safe


def register(mcp) -> None:
    @mcp.tool()
    def python_import_fix(project: str, path_filter: str = ".") -> str:
        """Remove unused imports with autoflake, then sort imports with isort."""
        path = str(PROJECT_ROOT / project)
        results = []
        if cmd_exists("autoflake"):
            results.append(
                "=== autoflake ===\n"
                + run_safe(
                    ["autoflake", "--in-place", "--remove-all-unused-imports", "--recursive", path_filter],
                    path,
                    "autoflake",
                    timeout=120,
                )
            )
        else:
            results.append("[autoflake not installed]")
        if cmd_exists("isort"):
            results.append("=== isort ===\n" + run_safe(["isort", path_filter], path, "isort", timeout=120))
        else:
            results.append("[isort not installed]")
        return "\n".join(results)

    @mcp.tool()
    def python_type_check(project: str, path_filter: str = ".") -> str:
        """Run mypy on Python code."""
        if not cmd_exists("mypy"):
            return "[mypy not installed]"
        return run_safe(["mypy", path_filter], str(PROJECT_ROOT / project), "mypy output", timeout=120, head_tail=True)

    @mcp.tool()
    def python_dead_code(project: str, path_filter: str = ".") -> str:
        """Run vulture on Python code."""
        if not cmd_exists("vulture"):
            return "[vulture not installed]"
        return run_safe(["vulture", path_filter], str(PROJECT_ROOT / project), "vulture output", timeout=120, head_tail=True)

    @mcp.tool()
    def python_complexity(project: str, path_filter: str = ".") -> str:
        """Run radon complexity metrics."""
        if not cmd_exists("radon"):
            return "[radon not installed]"
        return run_safe(["radon", "cc", "-s", "-a", path_filter], str(PROJECT_ROOT / project), "radon output", head_tail=True)

    @mcp.tool()
    def python_dependency_tree(project: str) -> str:
        """Show Python dependency tree with pipdeptree."""
        if not cmd_exists("pipdeptree"):
            return "[pipdeptree not installed]"
        return run_safe(["pipdeptree"], str(PROJECT_ROOT / project), "pipdeptree output", head_tail=True)

    @mcp.tool()
    def python_format(project: str, path_filter: str = ".") -> str:
        """Run autopep8 in place on Python files."""
        if not cmd_exists("autopep8"):
            return "[autopep8 not installed]"
        return run_safe(["autopep8", "--in-place", "--recursive", path_filter], str(PROJECT_ROOT / project), "autopep8", timeout=120)
