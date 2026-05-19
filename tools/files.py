from __future__ import annotations

import re
import time
from pathlib import Path

from core.audit import audit_event
from core.paths import UnsafePathError, safe_project_file, safe_project_path
from core.permissions import PermissionDenied, check_permission
from core.security import is_sensitive_path
from core.runtime import MAX_LINES_FULL, load_cache, run_safe, save_cache, trim


def _cache_key(project: str, file_path: str, allow_sensitive: bool = False) -> str:
    full_path = safe_project_file(project, file_path, allow_sensitive=allow_sensitive)
    return str(full_path)


def _get_mtime(project: str, file_path: str, allow_sensitive: bool = False) -> float:
    try:
        return safe_project_file(project, file_path, allow_sensitive=allow_sensitive).stat().st_mtime
    except (FileNotFoundError, UnsafePathError):
        return 0.0


def cache_get(project: str, file_path: str) -> str | None:
    try:
        key = _cache_key(project, file_path)
    except UnsafePathError:
        return None
    cache = load_cache()
    if key not in cache:
        return None
    entry = cache[key]
    if entry.get('mtime') != _get_mtime(project, file_path):
        del cache[key]
        save_cache(cache)
        return None
    return entry['content']


def cache_set(project: str, file_path: str, content: str) -> None:
    if is_sensitive_path(file_path):
        return
    cache = load_cache()
    cache[_cache_key(project, file_path)] = {
        'content': content,
        'mtime': _get_mtime(project, file_path),
        'cached': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    save_cache(cache)


def cache_evict(project: str, file_path: str) -> None:
    try:
        key = _cache_key(project, file_path, allow_sensitive=True)
    except UnsafePathError:
        return
    cache = load_cache()
    if key in cache:
        del cache[key]
        save_cache(cache)


def read_project_file(
    project: str,
    file_path: str,
    start_line: int = 1,
    end_line: int = 0,
    allow_sensitive: bool = False,
) -> str:
    try:
        full_path = safe_project_file(project, file_path, must_exist=True, allow_sensitive=allow_sensitive)
    except UnsafePathError as exc:
        return f"[Unsafe path: {exc}]"

    try:
        raw = full_path.read_text(errors='replace')
        lines = raw.splitlines()
        total = len(lines)
        if start_line == 1 and end_line == 0 and total > MAX_LINES_FULL:
            return (
                f"[{file_path} has {total} lines - too large to read in full]\n\n"
                'To read efficiently:\n'
                f"  1. Call file_outline('{project}', '{file_path}') to see structure\n"
                f"  2. Call read_file('{project}', '{file_path}', start_line=N, end_line=M) for the section you need\n"
                f"  3. Or call search_files('{project}', 'pattern') to locate specific code"
            )
        if start_line == 1 and end_line == 0 and not allow_sensitive:
            cached = cache_get(project, file_path)
            if cached is not None:
                return f"[cache hit - {file_path}]\n{trim(cached, file_path)}"
            cache_set(project, file_path, raw)
        chunk = lines[start_line - 1:end_line if end_line > 0 else None]
        content = '\n'.join(f"{i + start_line:4d}: {line}" for i, line in enumerate(chunk))
        audit_event('file_read', project=project, file_path=file_path, start_line=start_line, end_line=end_line)
        return trim(content, file_path, head_tail=True)
    except Exception as exc:
        return f"[Error reading file: {exc}]"


def write_project_file(project: str, file_path: str, content: str, confirm: bool = False, dry_run: bool = False) -> str:
    try:
        check_permission('write', tool='write_file', confirm=confirm)
        full_path = safe_project_file(project, file_path, allow_sensitive=False)
    except PermissionDenied as exc:
        return str(exc)
    except UnsafePathError as exc:
        return f"[Unsafe path: {exc}]"

    line_count = len(content.splitlines())
    if dry_run:
        audit_event('file_write_dry_run', project=project, file_path=file_path, chars=len(content), lines=line_count)
        return f"[Dry run] Would write {file_path} ({len(content)} chars, {line_count} lines)"

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')
        cache_evict(project, file_path)
        audit_event('file_write', project=project, file_path=file_path, chars=len(content), lines=line_count)
        return f"[Written: {file_path} ({len(content)} chars, {line_count} lines) - cache invalidated]"
    except Exception as exc:
        return f"[Error writing file: {exc}]"


def _safe_relative(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and '..' not in path.parts


def register(mcp) -> None:
    @mcp.tool()
    def file_outline(project: str, file_path: str, allow_sensitive: bool = False) -> str:
        try:
            full_path = safe_project_file(project, file_path, must_exist=True, allow_sensitive=allow_sensitive)
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"
        try:
            lines = full_path.read_text(errors='replace').splitlines()
            ext = Path(file_path).suffix.lower()
            if ext == '.py':
                pattern = re.compile(r'^(class |def |async def )')
            elif ext in ('.js', '.ts', '.jsx', '.tsx'):
                pattern = re.compile(r'^(export |function |class |const \w+ = )')
            elif ext in ('.go',):
                pattern = re.compile(r'^(func |type |var |const )')
            elif ext in ('.rs',):
                pattern = re.compile(r'^(pub |fn |struct |impl |enum |trait )')
            else:
                pattern = re.compile(r'^\S')
            hits = [f"L{i + 1:4d}: {line.rstrip()}" for i, line in enumerate(lines) if pattern.match(line)]
            if not hits:
                return f"{file_path} ({len(lines)} lines) - no top-level definitions found. Use read_file() directly."
            return f"{file_path} ({len(lines)} lines)\n\n" + '\n'.join(hits)
        except Exception as exc:
            return f"[Error reading file: {exc}]"

    @mcp.tool()
    def read_file(project: str, file_path: str, start_line: int = 1, end_line: int = 0, allow_sensitive: bool = False) -> str:
        return read_project_file(project, file_path, start_line, end_line, allow_sensitive=allow_sensitive)

    @mcp.tool()
    def write_file(project: str, file_path: str, content: str, confirm: bool = False, dry_run: bool = False) -> str:
        return write_project_file(project, file_path, content, confirm=confirm, dry_run=dry_run)

    @mcp.tool()
    def cache_list(project: str = '') -> str:
        cache = load_cache()
        entries = [(k, v) for k, v in cache.items() if not project or project in k]
        if not entries:
            return '[No cached files]'
        lines = [f"{k}  (cached: {v['cached']})" for k, v in sorted(entries)]
        return f"{len(lines)} cached file(s):\n" + '\n'.join(lines)

    @mcp.tool()
    def cache_invalidate(project: str, file_path: str) -> str:
        cache_evict(project, file_path)
        return f"[Cache invalidated: {file_path}]"

    @mcp.tool()
    def cache_clear(project: str = '') -> str:
        cache = load_cache()
        if project:
            keys = [k for k in cache if project in k]
            for key in keys:
                del cache[key]
            save_cache(cache)
            return f"[Cleared {len(keys)} cache entries for {project}]"
        count = len(cache)
        save_cache({})
        return f"[Cleared all {count} cache entries]"

    @mcp.tool()
    def search_files(project: str, pattern: str, file_glob: str = '') -> str:
        try:
            path = str(safe_project_path(project))
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"
        if file_glob and not _safe_relative(file_glob):
            return '[Unsafe path: file_glob must be relative]'
        if run_safe(['which', 'rg']).startswith('[Command not found'):
            cmd = ['grep', '-RIn', '--exclude-dir=.git', '--exclude-dir=node_modules']
            if file_glob:
                cmd += [f'--include={file_glob}']
            cmd += [pattern, '.']
        else:
            cmd = ['rg', '--line-number', '--no-heading']
            if file_glob:
                cmd += ['--glob', file_glob]
            cmd += [pattern, '.']
        return run_safe(cmd, path, f"search '{pattern}'", head_tail=True)
