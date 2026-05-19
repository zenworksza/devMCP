from __future__ import annotations

import re

from core.audit import audit_event
from core.paths import UnsafePathError, safe_project_cwd, safe_project_file
from core.permissions import PermissionDenied, check_permission
from core.runtime import run_safe, telegram_send


def _err(exc: Exception) -> str:
    return str(exc) if isinstance(exc, PermissionDenied) else f"[Unsafe path: {exc}]"


def register(mcp) -> None:
    @mcp.tool()
    def docker_compose_ps(project: str) -> str:
        try:
            return run_safe(['docker', 'compose', 'ps'], safe_project_cwd(project), 'docker ps')
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"

    @mcp.tool()
    def docker_compose_logs(project: str, service: str, lines: int = 50) -> str:
        try:
            return run_safe(['docker', 'compose', 'logs', '--tail', str(min(lines, 200)), service], safe_project_cwd(project), f'{service} logs', head_tail=True)
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"

    @mcp.tool()
    def docker_compose_build(project: str, service: str = '', confirm: bool = False, dry_run: bool = False) -> str:
        try:
            check_permission('docker', tool='docker_compose_build', confirm=confirm)
            cwd = safe_project_cwd(project)
        except (PermissionDenied, UnsafePathError) as exc:
            return _err(exc)
        cmd = ['docker', 'compose', 'build'] + ([service] if service else [])
        audit_event('docker_build', project=project, service=service, dry_run=dry_run)
        if dry_run:
            return f"[Dry run] Would run: {' '.join(cmd)} in {cwd}"
        return run_safe(cmd, cwd, 'docker build', timeout=300)

    @mcp.tool()
    def docker_compose_restart(project: str, service: str = '', confirm: bool = False, dry_run: bool = False) -> str:
        try:
            check_permission('docker', tool='docker_compose_restart', confirm=confirm)
            cwd = safe_project_cwd(project)
        except (PermissionDenied, UnsafePathError) as exc:
            return _err(exc)
        cmd = ['docker', 'compose', 'restart'] + ([service] if service else [])
        audit_event('docker_restart', project=project, service=service, dry_run=dry_run)
        if dry_run:
            return f"[Dry run] Would run: {' '.join(cmd)} in {cwd}"
        return run_safe(cmd, cwd, 'docker restart')

    @mcp.tool()
    def deploy_local(project: str, service: str = '', run_tests_first: bool = False, confirm: bool = False, dry_run: bool = False) -> str:
        try:
            check_permission('docker', tool='deploy_local', confirm=confirm)
            check_permission('deploy', tool='deploy_local', confirm=confirm)
            cwd = safe_project_cwd(project)
        except (PermissionDenied, UnsafePathError) as exc:
            return _err(exc)
        commands = []
        if run_tests_first:
            commands.append(['pytest', '--tb=short', '-q'])
        commands.append(['docker', 'compose', 'build'] + ([service] if service else []))
        commands.append(['docker', 'compose', 'up', '-d'] + (['--no-deps', service] if service else []))
        commands.append(['docker', 'compose', 'ps'])
        audit_event('deploy_local', project=project, service=service, run_tests_first=run_tests_first, dry_run=dry_run)
        if dry_run:
            return '[Dry run]\n' + '\n'.join(' '.join(cmd) for cmd in commands)

        results = []
        cmd_index = 0
        if run_tests_first:
            test_out = run_safe(commands[0], cwd, 'pytest', timeout=180)
            results.append(f'=== Tests ===\n{test_out}')
            if 'failed' in test_out.lower() or 'error' in test_out.lower():
                telegram_send(f'{project} - deploy aborted, tests failed.\n{test_out[:400]}')
                return '\n'.join(results) + '\n[Deploy aborted - fix failing tests first]'
            cmd_index = 1
        results.append(f"=== Build ===\n{run_safe(commands[cmd_index], cwd, 'build', timeout=300)}")
        results.append(f"=== Up ===\n{run_safe(commands[cmd_index + 1], cwd, 'up', timeout=120)}")
        ps_out = run_safe(commands[cmd_index + 2], cwd, 'docker ps')
        results.append(f'=== Status ===\n{ps_out}')
        telegram_send(f'{project} - local deploy complete.\n{ps_out[:300]}')
        return '\n'.join(results)

    @mcp.tool()
    def audit_named_volumes(project: str) -> str:
        try:
            compose_path = safe_project_file(project, 'docker-compose.yml', must_exist=True, allow_sensitive=True)
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"
        content = compose_path.read_text(encoding='utf-8', errors='replace')
        matches = re.findall(r'^\s+- (\.\.?/[^:"\s]+:[^"\s]+)', content, re.MULTILINE)
        if not matches:
            return '[No bind mounts found]'
        lines = [f'Found {len(matches)} bind mount(s) to review:']
        for match in matches:
            lines.append(f'  {match}')
        lines += ['', 'Convert code dirs to named volumes + Dockerfile COPY.', 'Keep config file mounts as bind mounts.']
        return '\n'.join(lines)
