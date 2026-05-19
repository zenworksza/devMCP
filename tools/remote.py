from __future__ import annotations

import time
from pathlib import Path

from core.audit import audit_event
from core.permissions import PermissionDenied, check_permission
from core.remote_actions import build_remote_command
from core.runtime import load_config, load_remotes, run_safe, save_remotes, telegram_send


def _validate_remote(project: str) -> dict | str:
    remotes = load_remotes()
    if project not in remotes:
        return f"[No remote for {project}. Use remote_add() first.]"
    cfg = remotes[project]
    if not cfg.get('host') or not cfg.get('user'):
        return '[Invalid remote configuration: host and user are required]'
    try:
        port = int(cfg.get('port', 22))
    except (TypeError, ValueError):
        return '[Invalid remote configuration: port must be numeric]'
    if port < 1 or port > 65535:
        return '[Invalid remote configuration: port must be 1-65535]'
    key_path = Path(str(cfg.get('ssh_key_path', ''))).expanduser()
    if not key_path.exists():
        return f"[Invalid remote configuration: ssh key not found at {key_path}]"
    cfg['port'] = port
    cfg['ssh_key_path'] = str(key_path)
    return cfg


def _ssh(project: str, command: str, timeout: int = 60, dry_run: bool = False) -> str:
    cfg = _validate_remote(project)
    if isinstance(cfg, str):
        return cfg
    cmd = [
        'ssh',
        '-i', cfg['ssh_key_path'],
        '-p', str(cfg['port']),
        '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'BatchMode=yes',
        '-o', 'IdentitiesOnly=yes',
        f"{cfg['user']}@{cfg['host']}",
        command,
    ]
    if dry_run:
        return f"[Dry run] Would SSH to {cfg['user']}@{cfg['host']}:{cfg['port']}\nCommand: {command}"
    return run_safe(cmd, label=f'ssh:{project}', timeout=timeout)


def _check(action: str, tool: str, confirm: bool) -> str | None:
    try:
        check_permission('remote', tool=tool, confirm=confirm)
        if action in {'docker_build', 'docker_up', 'docker_restart', 'git_pull'}:
            check_permission('deploy', tool=tool, confirm=confirm)
        if action == 'service_restart':
            check_permission('dangerous', tool=tool, confirm=confirm)
    except PermissionDenied as exc:
        return str(exc)
    return None


def register(mcp) -> None:
    @mcp.tool()
    def remote_add(project: str, host: str, user: str, ssh_key_path: str = '', port: int = 22, confirm: bool = False) -> str:
        try:
            check_permission('remote', tool='remote_add', confirm=confirm)
        except PermissionDenied as exc:
            return str(exc)
        key_path = Path(ssh_key_path or str(Path.home() / '.ssh' / 'id_rsa')).expanduser()
        if not host or not user:
            return '[host and user are required]'
        if port < 1 or port > 65535:
            return '[port must be between 1 and 65535]'
        if not key_path.exists():
            return f"[ssh key not found: {key_path}]"
        remotes = load_remotes()
        remotes[project] = {
            'host': host,
            'user': user,
            'port': port,
            'ssh_key_path': str(key_path),
            'added': time.strftime('%Y-%m-%dT%H:%M:%S'),
        }
        save_remotes(remotes)
        audit_event('remote_add', project=project, host=host, user=user, port=port)
        return f"[Remote registered: {user}@{host}:{port} for {project}]"

    @mcp.tool()
    def remote_list() -> str:
        remotes = load_remotes()
        if not remotes:
            return '[No remotes registered. Use remote_add() first.]'
        return '\n'.join(f"{project}: {cfg['user']}@{cfg['host']}:{cfg['port']}" for project, cfg in remotes.items())

    @mcp.tool()
    def remote_remove(project: str) -> str:
        remotes = load_remotes()
        if project not in remotes:
            return f"[No remote for {project}]"
        del remotes[project]
        save_remotes(remotes)
        audit_event('remote_remove', project=project)
        return f"[Remote removed: {project}]"

    @mcp.tool()
    def remote_exec(project: str, action: str, remote_path: str = '', service: str = '', branch: str = 'main', lines: int = 50, log_path: str = '', confirm: bool = False, dry_run: bool = False) -> str:
        denial = _check(action, 'remote_exec', confirm)
        if denial:
            return denial
        try:
            command = build_remote_command(action, remote_path=remote_path, service=service, branch=branch, lines=lines, log_path=log_path)
        except ValueError as exc:
            return f"[Blocked: {exc}]"
        audit_event('remote_exec', project=project, action=action, remote_path=remote_path, service=service, branch=branch, lines=lines, dry_run=dry_run)
        timeout = 300 if action in {'docker_build', 'docker_up'} else 60
        return _ssh(project, command, timeout=timeout, dry_run=dry_run)

    @mcp.tool()
    def remote_raw_shell(project: str, command: str, confirm: bool = False, dry_run: bool = False) -> str:
        config = load_config()
        if not config.get('allow_raw_remote_shell', False):
            return '[Blocked: raw remote shell is disabled in config.json]'
        try:
            check_permission('remote', tool='remote_raw_shell', confirm=confirm)
            check_permission('dangerous', tool='remote_raw_shell', confirm=confirm)
        except PermissionDenied as exc:
            return str(exc)
        audit_event('remote_raw_shell', project=project, dry_run=dry_run)
        return _ssh(project, command, timeout=300, dry_run=dry_run)

    @mcp.tool()
    def remote_git_pull(project: str, remote_path: str, branch: str = 'main', confirm: bool = False, dry_run: bool = False) -> str:
        return remote_exec(project, 'git_pull', remote_path=remote_path, branch=branch, confirm=confirm, dry_run=dry_run)

    @mcp.tool()
    def remote_rebuild(project: str, remote_path: str, service: str = '', confirm: bool = False, dry_run: bool = False) -> str:
        build = remote_exec(project, 'docker_build', remote_path=remote_path, service=service, confirm=confirm, dry_run=dry_run)
        up = remote_exec(project, 'docker_up', remote_path=remote_path, service=service, confirm=confirm, dry_run=dry_run)
        ps = remote_exec(project, 'docker_ps', remote_path=remote_path, confirm=confirm, dry_run=dry_run)
        if not dry_run:
            telegram_send(f'{project} - remote rebuild complete.\n{ps[:400]}')
        return f'=== Build ===\n{build}\n=== Up ===\n{up}\n=== Status ===\n{ps}'

    @mcp.tool()
    def remote_logs(project: str, remote_path: str, service: str, lines: int = 50) -> str:
        denial = _check('docker_logs', 'remote_logs', False)
        if denial:
            return denial
        return remote_exec(project, 'docker_logs', remote_path=remote_path, service=service, lines=lines)

    @mcp.tool()
    def remote_deploy(project: str, remote_path: str, branch: str = 'main', service: str = '', confirm: bool = False, dry_run: bool = False) -> str:
        pull = remote_exec(project, 'git_pull', remote_path=remote_path, branch=branch, confirm=confirm, dry_run=dry_run)
        rebuild = remote_rebuild(project, remote_path, service, confirm=confirm, dry_run=dry_run)
        return f'=== Pull ===\n{pull}\n=== Rebuild ===\n{rebuild}'
