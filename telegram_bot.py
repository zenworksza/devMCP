"""Safe Telegram bot for devMCP."""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import urllib.parse
import urllib.request
from hashlib import sha256
from pathlib import Path

from core.audit import audit_event
from core.memory_store import memory_get, memory_list
from core.paths import UnsafePathError, safe_project_cwd
from core.permissions import PermissionDenied, check_permission
from core.runtime import load_config, run_safe

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
POLL_INTERVAL = 2
MACHINE = socket.gethostname()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("telegram-bot")

HELP_TEXT = f"""
{MACHINE} — Dev Agent Commands

Deploy:
  deploy <project> --confirm
  remote deploy <project> <path> --confirm

Git:
  git status <project>
  git pull <project> [--confirm]
  git push <project> <message> --confirm

Docker:
  status <project>
  logs <project> <service> [lines]

Memory:
  memory list [namespace] [prefix]
  memory get <key>
  memory get <namespace> <key>

Agents:
  kimi: <prompt>
  gemini: <prompt>
  codex: <prompt>
  codex-danger: <prompt>

Other:
  help
""".strip()


def tg_request(method: str, params: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=15) as response:
            return json.loads(response.read())
    except Exception as exc:
        log.error("Telegram API error (%s): %s", method, exc)
        return {}


def send(text: str) -> None:
    if not text or not text.strip():
        return
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [""]
    for chunk in chunks:
        tg_request("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": chunk})


def get_updates(offset: int) -> list:
    result = tg_request("getUpdates", {"offset": offset, "timeout": 30, "allowed_updates": ["message"]})
    return result.get("result", [])


def run(cmd: list[str], cwd: str | None = None, timeout: int = 120) -> str:
    return run_safe(cmd, cwd=cwd, timeout=timeout)


def run_agent(agent: str, prompt: str, dangerous: bool = False) -> str:
    config = load_config()
    if agent == "kimi":
        return run(["kimi", "--quiet", "--afk", "-p", prompt], timeout=300)
    if agent == "gemini":
        return run(["gemini", "-p", prompt], timeout=300)
    if agent == "codex":
        cmd = ["codex", "exec", "-s", "workspace-write", "-C", str(Path.home() / "workspaces"), prompt]
        if dangerous:
            if not config.get("allow_codex_dangerous_bypass", False):
                return "[Blocked: codex dangerous bypass is disabled in config.json]"
            cmd.insert(4, "--dangerously-bypass-approvals-and-sandbox")
        return run(cmd, timeout=300)
    return f"[Unknown agent: {agent}]"


def _confirm_required(base: str) -> str:
    return f"[Confirmation required. Retry as: {base}]"


def dispatch(text: str) -> str:
    text = text.strip()
    lower = text.lower()
    parts = text.split()
    config = load_config()
    if not parts:
        return "[Empty message]"
    if lower == "help":
        return HELP_TEXT
    for agent in ("kimi", "gemini", "codex", "codex-danger"):
        if lower.startswith(f"{agent}:"):
            prompt = text[len(agent) + 1:].strip()
            if not prompt:
                return f"[Usage: {agent}: <your prompt>]"
            dangerous = agent == "codex-danger"
            send(f"Sending to {agent} on {MACHINE}...")
            return run_agent("codex" if dangerous else agent, prompt, dangerous=dangerous)
    if parts[0].lower() == "deploy" and len(parts) >= 2:
        project = parts[1]
        if "--confirm" not in parts:
            return _confirm_required(f"deploy {project} --confirm")
        try:
            check_permission("docker", tool="telegram deploy", confirm=True)
            check_permission("deploy", tool="telegram deploy", confirm=True)
            path = safe_project_cwd(project)
        except (PermissionDenied, UnsafePathError) as exc:
            return str(exc) if isinstance(exc, PermissionDenied) else f"[Unsafe path: {exc}]"
        build = run(["docker", "compose", "build"], path, timeout=300)
        up = run(["docker", "compose", "up", "-d"], path, timeout=120)
        ps = run(["docker", "compose", "ps"], path)
        return f"=== Build ===\n{build}\n\n=== Up ===\n{up}\n\n=== Status ===\n{ps}"
    if lower.startswith("remote deploy") and len(parts) >= 4:
        project = parts[2]
        remote_path = parts[3]
        if "--confirm" not in parts:
            return _confirm_required(f"remote deploy {project} {remote_path} --confirm")
        remotes_file = Path.home() / "mcp-dev-server" / "remote_servers.json"
        if not remotes_file.exists():
            return "[No remote servers registered. Use remote_add() in the MCP server first.]"
        remotes = json.loads(remotes_file.read_text())
        if project not in remotes:
            return f"[No remote registered for {project}]"
        cfg = remotes[project]
        ssh_base = [
            "ssh",
            "-i",
            cfg["ssh_key_path"],
            "-p",
            str(cfg["port"]),
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            f"{cfg['user']}@{cfg['host']}",
        ]
        pull = run(ssh_base + [f"cd {remote_path} && git pull origin main"], timeout=60)
        rebuild = run(ssh_base + [f"cd {remote_path} && docker compose build"], timeout=300)
        up = run(ssh_base + [f"cd {remote_path} && docker compose up -d"], timeout=120)
        ps = run(ssh_base + [f"cd {remote_path} && docker compose ps"])
        return f"=== Pull ===\n{pull}\n\n=== Build ===\n{rebuild}\n\n=== Up ===\n{up}\n\n=== Status ===\n{ps}"
    if parts[0].lower() == "status" and len(parts) >= 2:
        try:
            return run(["docker", "compose", "ps"], safe_project_cwd(parts[1]))
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"
    if parts[0].lower() == "logs" and len(parts) >= 3:
        try:
            lines = str(min(int(parts[3]), 200)) if len(parts) >= 4 and parts[3].isdigit() else "50"
            return run(["docker", "compose", "logs", "--tail", lines, parts[2]], safe_project_cwd(parts[1]))
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"
    if lower.startswith("git status") and len(parts) >= 3:
        try:
            return run(["git", "status", "--short"], safe_project_cwd(parts[2]))
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"
    if lower.startswith("git pull") and len(parts) >= 3:
        project = parts[2]
        confirm = "--confirm" in parts
        try:
            check_permission("git", tool="telegram git pull", confirm=confirm)
            return run(["git", "pull"], safe_project_cwd(project))
        except PermissionDenied:
            return _confirm_required(f"git pull {project} --confirm")
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"
    if lower.startswith("git push") and len(parts) >= 4:
        project = parts[2]
        if "--confirm" not in parts:
            return _confirm_required(f"git push {project} <message> --confirm")
        message = " ".join([p for p in parts[3:] if p != "--confirm"])
        try:
            check_permission("git", tool="telegram git push", confirm=True)
            check_permission("write", tool="telegram git push", confirm=True)
            path = safe_project_cwd(project)
        except (PermissionDenied, UnsafePathError) as exc:
            return str(exc) if isinstance(exc, PermissionDenied) else f"[Unsafe path: {exc}]"
        run(["git", "add", "-A"], path)
        commit = run(["git", "commit", "-m", message], path)
        run(["git", "checkout", "-B", "staging"], path)
        push = run(["git", "push", "origin", "staging", "--force-with-lease"], path, timeout=60)
        return f"{commit}\n{push}\nPushed to staging. Open a PR to merge to main."
    if lower.startswith("memory list"):
        namespace = parts[2] if len(parts) >= 3 else "general"
        prefix = parts[3] if len(parts) >= 4 else ""
        rows = memory_list(namespace, prefix)
        if not rows:
            return "[No memory entries found]"
        return "\n".join(f"{k}  ({v['updated']})" for k, v in rows)
    if lower.startswith("memory get") and len(parts) >= 3:
        if len(parts) >= 4:
            namespace, key = parts[2], parts[3]
        else:
            namespace, key = "general", parts[2]
        entry = memory_get(namespace, key)
        if not entry:
            return f"[No entry for key: {namespace}:{key}]"
        return f"[Updated: {entry['updated']}]\n{entry['value']}"
    if config.get("allow_telegram_codex_fallback", False):
        return run_agent("codex", text)
    return "[Unknown command. Type help. To send to Codex, use codex: <prompt>.]"


def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set.")
        sys.exit(1)
    send(f"{MACHINE} agent online. Type help for commands.")
    offset = 0
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "").strip()
                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue
                if not text:
                    continue
                audit_event(
                    "telegram_command",
                    machine=MACHINE,
                    chat_id_hash=sha256(chat_id.encode()).hexdigest()[:12],
                    command_class=text.split()[0].lower(),
                    accepted=True,
                )
                try:
                    response = dispatch(text)
                except Exception as exc:
                    audit_event("telegram_command_error", machine=MACHINE, error=str(exc))
                    response = f"[Error processing command: {exc}]"
                send(f"[{MACHINE}]\n{response}")
        except KeyboardInterrupt:
            send(f"{MACHINE} agent going offline.")
            break
        except Exception as exc:
            log.error("Polling error: %s", exc)
        import time
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
