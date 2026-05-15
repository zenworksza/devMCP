from __future__ import annotations

from core.runtime import PROJECT_ROOT, cmd_exists, run_safe


def register(mcp) -> None:
    @mcp.tool()
    def js_dependency_graph(project: str, path_filter: str = ".") -> str:
        """Generate a JS/TS dependency graph summary with madge."""
        if not cmd_exists("madge"):
            return "[madge not installed]"
        return run_safe(["madge", "--summary", path_filter], str(PROJECT_ROOT / project), "madge output", timeout=120)

    @mcp.tool()
    def js_circular_deps(project: str, path_filter: str = ".") -> str:
        """Find JS/TS circular dependencies with madge."""
        if not cmd_exists("madge"):
            return "[madge not installed]"
        return run_safe(["madge", "--circular", path_filter], str(PROJECT_ROOT / project), "madge output", timeout=120)

    @mcp.tool()
    def js_find_unused_exports(project: str) -> str:
        """Find unused TypeScript exports with ts-prune."""
        if not cmd_exists("ts-prune"):
            return "[ts-prune not installed]"
        return run_safe(["ts-prune"], str(PROJECT_ROOT / project), "ts-prune output", timeout=120, head_tail=True)

    @mcp.tool()
    def js_find_unused_deps(project: str) -> str:
        """Find unused npm dependencies with depcheck."""
        if not cmd_exists("depcheck"):
            return "[depcheck not installed]"
        return run_safe(["depcheck"], str(PROJECT_ROOT / project), "depcheck output", timeout=120, head_tail=True)

    @mcp.tool()
    def js_codemod(project: str, transform_path: str, target_path: str = ".") -> str:
        """Run a jscodeshift transform against JS/TS code."""
        if not cmd_exists("jscodeshift"):
            return "[jscodeshift not installed]"
        return run_safe(
            ["jscodeshift", "-t", transform_path, target_path],
            str(PROJECT_ROOT / project),
            "jscodeshift output",
            timeout=300,
            head_tail=True,
        )

    @mcp.tool()
    def js_typecheck(project: str) -> str:
        """Run TypeScript type checking if package scripts support it."""
        path = str(PROJECT_ROOT / project)
        return run_safe(["npm", "run", "typecheck", "--if-present"], path, "npm typecheck", timeout=120, head_tail=True)
