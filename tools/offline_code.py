from __future__ import annotations

from pathlib import Path

from core.paths import UnsafePathError, safe_project_cwd, safe_project_file
from core.runtime import cmd_exists, run_safe


def _missing(cmd: str) -> str:
    return f"[Command not found: {cmd}. Install it with tool_install('{cmd}') or the system package manager.]"


def register(mcp) -> None:
    @mcp.tool()
    def count_code(project: str, output: str = 'summary') -> str:
        try:
            cwd = safe_project_cwd(project)
        except UnsafePathError as exc:
            return f'[Unsafe path: {exc}]'
        if not cmd_exists('tokei'):
            return _missing('tokei')
        cmd = ['tokei', '.'] if output != 'json' else ['tokei', '--output', 'json', '.']
        return run_safe(cmd, cwd, 'tokei output', head_tail=True)

    @mcp.tool()
    def find_files(project: str, pattern: str = '', extension: str = '', max_results: int = 200) -> str:
        try:
            cwd = safe_project_cwd(project)
        except UnsafePathError as exc:
            return f'[Unsafe path: {exc}]'
        if cmd_exists('fd'):
            cmd = ['fd', '--type', 'f', '--max-results', str(min(max_results, 1000))]
            if extension:
                cmd += ['--extension', extension.lstrip('.')]
            cmd += [pattern or '.']
        elif cmd_exists('fdfind'):
            cmd = ['fdfind', '--type', 'f', '--max-results', str(min(max_results, 1000))]
            if extension:
                cmd += ['--extension', extension.lstrip('.')]
            cmd += [pattern or '.']
        else:
            name = f"*.{extension.lstrip('.')}" if extension else '*'
            cmd = ['find', '.', '-type', 'f', '-name', name]
        return run_safe(cmd, cwd, 'file list', head_tail=True)

    @mcp.tool()
    def preview_file(project: str, file_path: str, start_line: int = 1, lines: int = 120) -> str:
        try:
            target = safe_project_file(project, file_path, must_exist=True, allow_sensitive=True)
            cwd = safe_project_cwd(project)
        except UnsafePathError as exc:
            return f'[Unsafe path: {exc}]'
        end_line = start_line + max(1, min(lines, 300)) - 1
        bat_cmd = 'batcat' if cmd_exists('batcat') else 'bat' if cmd_exists('bat') else ''
        rel = str(target.relative_to(Path(cwd)))
        if bat_cmd:
            return run_safe([bat_cmd, '--style=numbers', '--color=never', f'--line-range={start_line}:{end_line}', rel], cwd, 'bat output', head_tail=True)
        return run_safe(['sed', '-n', f'{start_line},{end_line}p', rel], cwd, 'sed output', head_tail=True)
