from __future__ import annotations

from core.runtime import PROJECT_ROOT, cmd_exists, run_safe


def _missing(cmd: str) -> str:
    return f"[Command not found: {cmd}. Install it with tool_install('{cmd}') or the system package manager.]"


def register(mcp) -> None:
    @mcp.tool()
    def count_code(project: str, output: str = "summary") -> str:
        """Count code by language using tokei. output: summary or json."""
        if not cmd_exists("tokei"):
            return _missing("tokei")
        cmd = ["tokei", "."] if output != "json" else ["tokei", "--output", "json", "."]
        return run_safe(cmd, str(PROJECT_ROOT / project), "tokei output", head_tail=True)

    @mcp.tool()
    def find_files(project: str, pattern: str = "", extension: str = "", max_results: int = 200) -> str:
        """Find files quickly using fd, falling back to find."""
        path = str(PROJECT_ROOT / project)
        if cmd_exists("fd"):
            cmd = ["fd", "--type", "f", "--max-results", str(min(max_results, 1000))]
            if extension:
                cmd += ["--extension", extension.lstrip(".")]
            cmd += [pattern or "."]
        elif cmd_exists("fdfind"):
            cmd = ["fdfind", "--type", "f", "--max-results", str(min(max_results, 1000))]
            if extension:
                cmd += ["--extension", extension.lstrip(".")]
            cmd += [pattern or "."]
        else:
            name = f"*.{extension.lstrip('.')}" if extension else "*"
            cmd = ["find", ".", "-type", "f", "-name", name]
        return run_safe(cmd, path, "file list", head_tail=True)

    @mcp.tool()
    def preview_file(project: str, file_path: str, start_line: int = 1, lines: int = 120) -> str:
        """Preview a file with bat when available, otherwise sed."""
        path = PROJECT_ROOT / project
        end_line = start_line + max(1, min(lines, 300)) - 1
        bat_cmd = "batcat" if cmd_exists("batcat") else "bat" if cmd_exists("bat") else ""
        if bat_cmd:
            return run_safe(
                [bat_cmd, "--style=numbers", "--color=never", f"--line-range={start_line}:{end_line}", file_path],
                str(path),
                "bat output",
                head_tail=True,
            )
        return run_safe(["sed", "-n", f"{start_line},{end_line}p", file_path], str(path), "sed output", head_tail=True)

    @mcp.tool()
    def symbol_index(project: str, output_file: str = ".tags") -> str:
        """Build a ctags symbol index for a project."""
        ctags = "ctags" if cmd_exists("ctags") else "universal-ctags" if cmd_exists("universal-ctags") else ""
        if not ctags:
            return _missing("ctags")
        return run_safe(
            [ctags, "-R", "-f", output_file, "."],
            str(PROJECT_ROOT / project),
            "ctags output",
            timeout=120,
            head_tail=True,
        )

    @mcp.tool()
    def complexity_report(project: str, path_filter: str = ".", language: str = "python") -> str:
        """Run complexity analysis with lizard or radon."""
        path = str(PROJECT_ROOT / project)
        if cmd_exists("lizard"):
            return run_safe(["lizard", path_filter], path, "lizard output", timeout=120, head_tail=True)
        if language == "python" and cmd_exists("radon"):
            return run_safe(["radon", "cc", "-s", "-a", path_filter], path, "radon output", timeout=120, head_tail=True)
        return "[No complexity tool found. Install lizard or radon.]"

    @mcp.tool()
    def dead_code_scan(project: str, path_filter: str = ".") -> str:
        """Find likely dead Python code with vulture."""
        if not cmd_exists("vulture"):
            return _missing("vulture")
        return run_safe(["vulture", path_filter], str(PROJECT_ROOT / project), "vulture output", timeout=120, head_tail=True)

    @mcp.tool()
    def search_all(project: str, pattern: str) -> str:
        """Search text and supported binary/document files using ripgrep-all when installed."""
        if cmd_exists("rga"):
            return run_safe(["rga", "--line-number", pattern, "."], str(PROJECT_ROOT / project), "rga output", head_tail=True)
        if cmd_exists("rg"):
            return run_safe(["rg", "--line-number", pattern, "."], str(PROJECT_ROOT / project), "rg output", head_tail=True)
        return _missing("rg")

    @mcp.tool()
    def file_tree(project: str, max_depth: int = 3) -> str:
        """Show a shallow project file tree."""
        path = str(PROJECT_ROOT / project)
        if cmd_exists("tree"):
            return run_safe(["tree", "-a", "-L", str(min(max_depth, 6)), "-I", ".git|node_modules|__pycache__"], path, "tree output")
        return run_safe(["find", ".", "-maxdepth", str(min(max_depth, 6)), "-print"], path, "find output", head_tail=True)

    @mcp.tool()
    def command_benchmark(project: str, command: str, runs: int = 3) -> str:
        """Benchmark a simple project-local command with hyperfine."""
        if not cmd_exists("hyperfine"):
            return _missing("hyperfine")
        if any(token in command for token in [";", "&&", "||", "|", "$(", "`", ">", "<"]):
            return "[Blocked: command_benchmark accepts a single simple command, no shell operators.]"
        return run_safe(["hyperfine", "--runs", str(min(max(runs, 1), 20)), command], str(PROJECT_ROOT / project), "hyperfine")
