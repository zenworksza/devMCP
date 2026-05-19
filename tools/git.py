from __future__ import annotations

import re

from core.audit import audit_event
from core.paths import UnsafePathError, safe_new_project_name, safe_project_cwd
from core.permissions import PermissionDenied, check_permission
from core.runtime import PROJECT_ROOT, run_safe, telegram_send

_ALLOWED_REPO_URL = re.compile(r'^(https://|git@|ssh://)')


def _format_exc(exc: Exception) -> str:
    return str(exc) if isinstance(exc, PermissionDenied) else f"[Unsafe path: {exc}]"


def register(mcp) -> None:
    @mcp.tool()
    def list_projects() -> str:
        if not PROJECT_ROOT.exists():
            return f"[workspaces not found at {PROJECT_ROOT}]"
        return '\n'.join(p.name for p in sorted(PROJECT_ROOT.iterdir()) if p.is_dir())

    @mcp.tool()
    def git_status(project: str) -> str:
        try:
            return run_safe(['git', 'status', '--short'], safe_project_cwd(project), 'git status')
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"

    @mcp.tool()
    def git_diff(project: str, path_filter: str = '') -> str:
        try:
            cmd = ['git', 'diff'] + (['--', path_filter] if path_filter else [])
            return run_safe(cmd, safe_project_cwd(project), 'git diff', head_tail=True)
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"

    @mcp.tool()
    def git_log(project: str, n: int = 10) -> str:
        try:
            return run_safe(['git', 'log', '--oneline', f'-{min(n, 50)}'], safe_project_cwd(project), 'git log')
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"

    @mcp.tool()
    def git_pull(project: str, confirm: bool = False, dry_run: bool = False) -> str:
        try:
            check_permission('git', tool='git_pull', confirm=confirm)
            cwd = safe_project_cwd(project)
        except (PermissionDenied, UnsafePathError) as exc:
            return _format_exc(exc)
        cmd = ['git', 'pull']
        audit_event('git_pull', project=project, dry_run=dry_run)
        if dry_run:
            return f"[Dry run] Would run: {' '.join(cmd)} in {cwd}"
        return run_safe(cmd, cwd, 'git pull')

    @mcp.tool()
    def git_clone(repo_url: str, project_name: str, confirm: bool = False, dry_run: bool = False) -> str:
        try:
            check_permission('write', tool='git_clone', confirm=confirm)
            safe_name = safe_new_project_name(project_name)
        except (PermissionDenied, UnsafePathError) as exc:
            return _format_exc(exc)
        if not _ALLOWED_REPO_URL.match(repo_url):
            return '[Blocked: repo_url must start with https://, git@, or ssh://]'
        cmd = ['git', 'clone', repo_url, safe_name]
        target = PROJECT_ROOT / safe_name
        audit_event('git_clone', repo_url=repo_url, project_name=safe_name, dry_run=dry_run)
        if dry_run:
            return f"[Dry run] Would clone into {target}\nCommand: {' '.join(cmd)}"
        return run_safe(cmd, str(PROJECT_ROOT), 'git clone', timeout=120)

    @mcp.tool()
    def git_push_staging(project: str, commit_message: str, pr_description: str = '', confirm: bool = False, dry_run: bool = False) -> str:
        if not commit_message.strip():
            return '[Blocked: commit_message is required]'
        try:
            check_permission('git', tool='git_push_staging', confirm=confirm)
            check_permission('write', tool='git_push_staging', confirm=confirm)
            path = safe_project_cwd(project)
        except (PermissionDenied, UnsafePathError) as exc:
            return _format_exc(exc)
        commands = [
            ['git', 'add', '-A'],
            ['git', 'commit', '-m', commit_message],
            ['git', 'checkout', '-B', 'staging'],
            ['git', 'push', 'origin', 'staging', '--force-with-lease'],
        ]
        audit_event('git_push_staging', project=project, commit_message=commit_message, dry_run=dry_run)
        if dry_run:
            return '[Dry run]\n' + '\n'.join(' '.join(cmd) for cmd in commands)
        run_safe(commands[0], path)
        commit_out = run_safe(commands[1], path)
        if 'nothing to commit' in commit_out:
            return '[Nothing to commit - working tree clean]'
        run_safe(commands[2], path)
        push_out = run_safe(commands[3], path, timeout=60)
        remote_url = run_safe(['git', 'remote', 'get-url', 'origin'], path).strip()
        pr_link = ''
        if 'github.com' in remote_url:
            clean = re.sub(r'git@github\.com:', 'https://github.com/', remote_url).rstrip('.git')
            pr_link = f'{clean}/compare/staging?expand=1'
        msg = [f'{project} - staging updated', commit_message]
        if pr_description:
            msg.append(pr_description)
        if pr_link:
            msg.append(pr_link)
        msg.append('Please review and merge to main.')
        telegram_send('\n'.join(msg))
        return f'{commit_out}\n{push_out}\nTelegram notification sent.'
