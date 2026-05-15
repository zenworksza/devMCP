from __future__ import annotations

import time
from pathlib import Path

from core.runtime import load_remotes, run_safe, save_remotes, telegram_send


def _ssh(project: str, command: str, timeout: int = 60) -> str:
    remotes = load_remotes()
    if project not in remotes:
        return f"[No remote for {project}. Use remote_add() first.]"
    cfg = remotes[project]
    return run_safe(
        [
            "ssh",
            "-i",
            cfg["ssh_key_path"],
            "-p",
            str(cfg["port"]),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "BatchMode=yes",
            f"{cfg['user']}@{cfg['host']}",
            command,
        ],
        label=f"ssh:{project}",
        timeout=timeout,
    )


def register(mcp) -> None:
    @mcp.tool()
    def remote_add(project: str, host: str, user: str, ssh_key_path: str = "", port: int = 22) -> str:
        """
        Register a remote server for a project.
        Credentials stored once in remote_servers.json, reused by all remote_* tools.
        """
        remotes = load_remotes()
        remotes[project] = {
            "host": host,
            "user": user,
            "port": port,
            "ssh_key_path": ssh_key_path or str(Path.home() / ".ssh" / "id_rsa"),
            "added": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        save_remotes(remotes)
        return f"[Remote registered: {user}@{host}:{port} for {project}]"

    @mcp.tool()
    def remote_list() -> str:
        """List all registered remote servers."""
        remotes = load_remotes()
        if not remotes:
            return "[No remotes registered. Use remote_add() first.]"
        return "\n".join(f"{project}: {cfg['user']}@{cfg['host']}:{cfg['port']}" for project, cfg in remotes.items())

    @mcp.tool()
    def remote_remove(project: str) -> str:
        """Remove a registered remote server."""
        remotes = load_remotes()
        if project not in remotes:
            return f"[No remote for {project}]"
        del remotes[project]
        save_remotes(remotes)
        return f"[Remote removed: {project}]"

    @mcp.tool()
    def remote_exec(project: str, command: str) -> str:
        """Run a shell command on the registered remote server for a project."""
        return _ssh(project, command)

    @mcp.tool()
    def remote_git_pull(project: str, remote_path: str, branch: str = "main") -> str:
        """Git pull on the remote server."""
        return _ssh(
            project,
            f"cd {remote_path} && git fetch origin && git checkout {branch} && git pull origin {branch}",
            timeout=60,
        )

    @mcp.tool()
    def remote_rebuild(project: str, remote_path: str, service: str = "") -> str:
        """Docker compose build + up on remote. Sends Telegram notification."""
        svc = service or ""
        build = _ssh(project, f"cd {remote_path} && docker compose build {svc}".strip(), timeout=300)
        up = _ssh(project, f"cd {remote_path} && docker compose up -d {svc}".strip(), timeout=120)
        ps = _ssh(project, f"cd {remote_path} && docker compose ps")
        telegram_send(f"*{project}* - remote rebuild complete.\n```\n{ps[:400]}\n```")
        return f"=== Build ===\n{build}\n=== Up ===\n{up}\n=== Status ===\n{ps}"

    @mcp.tool()
    def remote_logs(project: str, remote_path: str, service: str, lines: int = 50) -> str:
        """Docker compose logs on remote server."""
        return _ssh(project, f"cd {remote_path} && docker compose logs --tail {min(lines, 200)} {service}")

    @mcp.tool()
    def remote_deploy(project: str, remote_path: str, branch: str = "main", service: str = "") -> str:
        """Full remote deploy: git pull -> rebuild -> notify. Run after merging staging -> main."""
        pull = remote_git_pull(project, remote_path, branch)
        rebuild = remote_rebuild(project, remote_path, service)
        return f"=== Pull ===\n{pull}\n=== Rebuild ===\n{rebuild}"
