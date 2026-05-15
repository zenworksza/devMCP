from __future__ import annotations

import re
import time
from pathlib import Path

from core.runtime import (
    CACHE_FILE,
    MAX_LINES_FULL,
    PROJECT_ROOT,
    cmd_exists,
    load_cache,
    run_safe,
    save_cache,
    trim,
)


def _cache_key(project: str, file_path: str) -> str:
    return f"{project}::{file_path}"


def _get_mtime(project: str, file_path: str) -> float:
    try:
        return (PROJECT_ROOT / project / file_path).stat().st_mtime
    except FileNotFoundError:
        return 0.0


def cache_get(project: str, file_path: str) -> str | None:
    cache = load_cache()
    key = _cache_key(project, file_path)
    if key not in cache:
        return None
    entry = cache[key]
    if entry.get("mtime") != _get_mtime(project, file_path):
        del cache[key]
        save_cache(cache)
        return None
    return entry["content"]


def cache_set(project: str, file_path: str, content: str) -> None:
    cache = load_cache()
    cache[_cache_key(project, file_path)] = {
        "content": content,
        "mtime": _get_mtime(project, file_path),
        "cached": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    save_cache(cache)


def cache_evict(project: str, file_path: str) -> None:
    cache = load_cache()
    key = _cache_key(project, file_path)
    if key in cache:
        del cache[key]
        save_cache(cache)


def read_project_file(project: str, file_path: str, start_line: int = 1, end_line: int = 0) -> str:
    full_path = PROJECT_ROOT / project / file_path
    if not full_path.exists():
        return f"[File not found: {full_path}]"

    try:
        raw = full_path.read_text(errors="replace")
        lines = raw.splitlines()
        total = len(lines)

        if start_line == 1 and end_line == 0 and total > MAX_LINES_FULL:
            return (
                f"[{file_path} has {total} lines - too large to read in full]\n\n"
                f"To read efficiently:\n"
                f"  1. Call file_outline('{project}', '{file_path}') to see structure\n"
                f"  2. Call read_file('{project}', '{file_path}', start_line=N, end_line=M) "
                f"for the section you need\n"
                f"  3. Or call search_files('{project}', 'pattern') to locate specific code"
            )

        if start_line == 1 and end_line == 0:
            cached = cache_get(project, file_path)
            if cached is not None:
                return f"[cache hit - {file_path}]\n{trim(cached, file_path)}"
            cache_set(project, file_path, raw)

        chunk = lines[start_line - 1 : end_line if end_line > 0 else None]
        content = "\n".join(f"{i + start_line:4d}: {line}" for i, line in enumerate(chunk))
        return trim(content, file_path, head_tail=True)
    except Exception as exc:
        return f"[Error reading file: {exc}]"


def write_project_file(project: str, file_path: str, content: str) -> str:
    full_path = PROJECT_ROOT / project / file_path
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        cache_evict(project, file_path)
        return f"[Written: {file_path} ({len(content)} chars, {len(content.splitlines())} lines) - cache invalidated]"
    except Exception as exc:
        return f"[Error writing file: {exc}]"


def register(mcp) -> None:
    @mcp.tool()
    def file_outline(project: str, file_path: str) -> str:
        """
        Return the structure of a file without its full content.
        Shows class/function definitions with line numbers.
        """
        full_path = PROJECT_ROOT / project / file_path
        if not full_path.exists():
            return f"[File not found: {full_path}]"

        try:
            lines = full_path.read_text(errors="replace").splitlines()
            ext = Path(file_path).suffix.lower()

            if ext == ".py":
                pattern = re.compile(r"^(class |def |async def )")
            elif ext in (".js", ".ts", ".jsx", ".tsx"):
                pattern = re.compile(r"^(export |function |class |const \w+ = )")
            elif ext in (".go",):
                pattern = re.compile(r"^(func |type |var |const )")
            elif ext in (".rs",):
                pattern = re.compile(r"^(pub |fn |struct |impl |enum |trait )")
            else:
                pattern = re.compile(r"^\S")

            hits = [
                f"L{i + 1:4d}: {line.rstrip()}"
                for i, line in enumerate(lines)
                if pattern.match(line)
            ]
            if not hits:
                return f"{file_path} ({len(lines)} lines) - no top-level definitions found. Use read_file() directly."
            return f"{file_path} ({len(lines)} lines)\n\n" + "\n".join(hits)
        except Exception as exc:
            return f"[Error reading file: {exc}]"

    @mcp.tool()
    def read_file(project: str, file_path: str, start_line: int = 1, end_line: int = 0) -> str:
        """
        Read a file or specific line range from a project.
        Files over 200 lines require start_line and end_line.
        """
        return read_project_file(project, file_path, start_line, end_line)

    @mcp.tool()
    def write_file(project: str, file_path: str, content: str) -> str:
        """
        Write content to a file on disk and invalidate its cache entry.
        After writing: run lint(), then deploy_local() to apply changes.
        """
        return write_project_file(project, file_path, content)

    @mcp.tool()
    def cache_list(project: str = "") -> str:
        """List cached files, optionally filtered by project."""
        cache = load_cache()
        entries = [(k, v) for k, v in cache.items() if not project or k.startswith(f"{project}::")]
        if not entries:
            return "[No cached files]"
        lines = [f"{k}  (cached: {v['cached']})" for k, v in sorted(entries)]
        return f"{len(lines)} cached file(s):\n" + "\n".join(lines)

    @mcp.tool()
    def cache_invalidate(project: str, file_path: str) -> str:
        """Manually evict a file from the cache."""
        cache_evict(project, file_path)
        return f"[Cache invalidated: {project}::{file_path}]"

    @mcp.tool()
    def cache_clear(project: str = "") -> str:
        """Clear file cache for a project, or all projects if project is empty."""
        cache = load_cache()
        if project:
            keys = [k for k in cache if k.startswith(f"{project}::")]
            for key in keys:
                del cache[key]
            save_cache(cache)
            return f"[Cleared {len(keys)} cache entries for {project}]"
        count = len(cache)
        CACHE_FILE.write_text("{}")
        return f"[Cleared all {count} cache entries]"

    @mcp.tool()
    def search_files(project: str, pattern: str, file_glob: str = "") -> str:
        """
        Search project files for a pattern. Uses ripgrep (rg) if available.
        """
        path = str(PROJECT_ROOT / project)
        if cmd_exists("rg"):
            cmd = ["rg", "--line-number", "--no-heading"]
            if file_glob:
                cmd += ["--glob", file_glob]
            cmd += [pattern, "."]
        else:
            cmd = ["grep", "-RIn", "--exclude-dir=.git", "--exclude-dir=node_modules"]
            if file_glob:
                cmd += [f"--include={file_glob}"]
            cmd += [pattern, "."]
        return run_safe(cmd, path, f"search '{pattern}'", head_tail=True)
