from __future__ import annotations

import shlex

ALLOWED_REMOTE_ACTIONS = {
    "system_info",
    "disk_usage",
    "memory_usage",
    "docker_ps",
    "docker_logs",
    "docker_build",
    "docker_up",
    "docker_restart",
    "git_status",
    "git_pull",
    "tail_log",
    "service_status",
    "service_restart",
}

_DANGEROUS_TOKENS = (";", "`", "$(", "|", ">", "<", "&&")
_REMOTE_DIR_ACTIONS = {
    "docker_ps",
    "docker_logs",
    "docker_build",
    "docker_up",
    "docker_restart",
    "git_status",
    "git_pull",
}


def _reject_shell_fragments(value: str, *, field: str) -> str:
    raw = str(value or "").strip()
    for token in _DANGEROUS_TOKENS:
        if token in raw:
            raise ValueError(f"{field} contains forbidden shell token: {token}")
    return raw


def _quote_path(value: str, *, field: str) -> str:
    raw = _reject_shell_fragments(value, field=field)
    if not raw:
        raise ValueError(f"{field} is required")
    return shlex.quote(raw)


def build_remote_command(
    action: str,
    *,
    remote_path: str = "",
    service: str = "",
    branch: str = "main",
    lines: int = 50,
    log_path: str = "",
) -> str:
    if action not in ALLOWED_REMOTE_ACTIONS:
        raise ValueError(f"unknown remote action: {action}")

    safe_lines = max(1, min(int(lines), 200))
    safe_service = _reject_shell_fragments(service, field="service")
    safe_branch = _reject_shell_fragments(branch, field="branch") or "main"

    if action in _REMOTE_DIR_ACTIONS:
        quoted_remote = _quote_path(remote_path, field="remote_path")
    else:
        quoted_remote = ""

    if action == "system_info":
        return "uname -a && uptime"
    if action == "disk_usage":
        return "df -h"
    if action == "memory_usage":
        return "free -h"
    if action == "docker_ps":
        return f"cd {quoted_remote} && docker compose ps"
    if action == "docker_logs":
        if not safe_service:
            raise ValueError("service is required for docker_logs")
        return f"cd {quoted_remote} && docker compose logs --tail {safe_lines} {shlex.quote(safe_service)}"
    if action == "docker_build":
        suffix = f" {shlex.quote(safe_service)}" if safe_service else ""
        return f"cd {quoted_remote} && docker compose build{suffix}"
    if action == "docker_up":
        suffix = f" {shlex.quote(safe_service)}" if safe_service else ""
        return f"cd {quoted_remote} && docker compose up -d{suffix}"
    if action == "docker_restart":
        suffix = f" {shlex.quote(safe_service)}" if safe_service else ""
        return f"cd {quoted_remote} && docker compose restart{suffix}"
    if action == "git_status":
        return f"cd {quoted_remote} && git status --short"
    if action == "git_pull":
        quoted_branch = shlex.quote(safe_branch)
        return (
            f"cd {quoted_remote} && git fetch origin && git checkout {quoted_branch}"
            f" && git pull origin {quoted_branch}"
        )
    if action == "tail_log":
        safe_log = _reject_shell_fragments(log_path, field="log_path")
        if not safe_log:
            raise ValueError("log_path is required for tail_log")
        if safe_log.startswith("/var/log/"):
            target = shlex.quote(safe_log)
        elif remote_path and not safe_log.startswith("/"):
            target = shlex.quote(f"{remote_path.rstrip('/')}/{safe_log.lstrip('/')}")
        else:
            raise ValueError("tail_log requires /var/log/* or a path under remote_path")
        return f"tail -n {safe_lines} {target}"
    if action == "service_status":
        if not safe_service:
            raise ValueError("service is required for service_status")
        return f"systemctl status {shlex.quote(safe_service)} --no-pager"
    if action == "service_restart":
        if not safe_service:
            raise ValueError("service is required for service_restart")
        return f"sudo systemctl restart {shlex.quote(safe_service)}"
    raise ValueError(f"unsupported remote action: {action}")
