"""
Telegram Bot — ~/mcp-dev-server/telegram_bot.py

Two-way communication between developer and dev agents via Telegram.
Each machine runs its own instance with its own bot token.

Commands:
  help                                 — show command list
  status <project>                     — docker compose ps
  logs <project> <service> [lines]     — docker compose logs
  git status <project>                 — git status
  git pull <project>                   — git pull
  git push <project> <message>         — push to staging + PR notification
  deploy <project>                     — local build + restart
  remote deploy <project> <path>       — remote git pull + rebuild
  memory list [prefix]                 — list memory keys
  memory get <key>                     — read a memory value
  kimi: <prompt>                       — delegate to Kimi CLI
  gemini: <prompt>                     — delegate to Gemini CLI
  codex: <prompt>                      — send to Codex CLI
  <anything else>                      — sent to Codex as plain prompt
"""

import os
import subprocess
import json
import logging
import sys
import socket
import urllib.request
import urllib.parse
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
PROJECT_ROOT     = Path.home() / "workspaces"
POLL_INTERVAL    = 2
MACHINE          = socket.gethostname()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("telegram-bot")

HELP_TEXT = f"""
*{MACHINE} — Dev Agent Commands*

*Deploy*
`deploy <project>` — local build + restart
`remote deploy <project> <path>` — remote git pull + rebuild

*Docker*
`status <project>` — docker compose ps
`logs <project> <service> [lines]` — service logs

*Git*
`git status <project>` — show changes
`git pull <project>` — pull latest
`git push <project> <message>` — push to staging + PR notification

*Memory*
`memory list [prefix]` — list memory keys
`memory get <key>` — read a memory value

*Agents*
`kimi: <prompt>` — delegate to Kimi
`gemini: <prompt>` — delegate to Gemini
`codex: <prompt>` — send to Codex

*Other*
`help` — show this message

_Anything else is sent to Codex as a plain prompt._
""".strip()


# ─── Telegram API ─────────────────────────────────────────────────────────────

def tg_request(method: str, params: dict = {}) -> dict:
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        log.error(f"Telegram API error ({method}): {e}")
        return {}


def send(text: str) -> None:
    """Send message to developer, splitting at 4000 chars if needed."""
    if not text or not text.strip():
        log.warning("send() called with empty text — skipping")
        return
    chunks = [text[i:i+4000] for i in range(0, max(len(text), 1), 4000)]
    for chunk in chunks:
        tg_request("sendMessage", {
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       chunk,
            "parse_mode": "Markdown",
        })


def get_updates(offset: int) -> list:
    result = tg_request("getUpdates", {
        "offset":          offset,
        "timeout":         30,
        "allowed_updates": ["message"],
    })
    return result.get("result", [])


# ─── CLI runners ──────────────────────────────────────────────────────────────

def run(cmd: list[str], cwd: str | None = None, timeout: int = 120) -> str:
    """Run a subprocess, return combined stdout+stderr, trimmed to 3000 chars."""
    log.info(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        # Codex puts response in stdout, header info in stderr — combine both
        out = result.stdout.strip()
        err = result.stderr.strip()
        combined = out if out else err  # prefer stdout if present
        if not combined:
            combined = "[No output]"
        log.info(f"Result ({len(combined)} chars): {combined[:200]!r}")
        return combined[:3000]
    except subprocess.TimeoutExpired:
        msg = f"[Timed out after {timeout}s]"
        log.error(msg)
        return msg
    except FileNotFoundError:
        msg = f"[Command not found: {cmd[0]}]"
        log.error(msg)
        return msg
    except Exception as e:
        msg = f"[Error: {e}]"
        log.error(msg)
        return msg


def run_agent(agent: str, prompt: str) -> str:
    """Dispatch a prompt to an agent CLI and return the response."""
    agents = {
        "kimi":   ["kimi",   "chat", "--", prompt],
        "gemini": ["gemini", "--",         prompt],
        "codex":  [
            "codex", "exec",
            "-s", "workspace-write",
            "--dangerously-bypass-approvals-and-sandbox",
            "-C", str(PROJECT_ROOT),
            prompt,
        ],
    }
    if agent not in agents:
        return f"[Unknown agent: {agent}]"
    return run(agents[agent], cwd=str(PROJECT_ROOT), timeout=300)


# ─── Command dispatcher ───────────────────────────────────────────────────────

def dispatch(text: str) -> str:
    text  = text.strip()
    lower = text.lower()
    parts = text.split()

    if not parts:
        return "[Empty message]"

    # ── help ──────────────────────────────────────────────────────────────────
    if lower == "help":
        return HELP_TEXT

    # ── agent prefix: kimi: / gemini: / codex: ───────────────────────────────
    for agent in ("kimi", "gemini", "codex"):
        if lower.startswith(f"{agent}:"):
            prompt = text[len(agent)+1:].strip()
            if not prompt:
                return f"[Usage: {agent}: <your prompt>]"
            send(f"⏳ Sending to *{agent}* on *{MACHINE}*...")
            return run_agent(agent, prompt)

    # ── deploy <project> ──────────────────────────────────────────────────────
    if parts[0].lower() == "deploy" and len(parts) >= 2:
        project = parts[1]
        path    = str(PROJECT_ROOT / project)
        send(f"⏳ Deploying *{project}* on *{MACHINE}*...")
        build = run(["docker", "compose", "build"], path, timeout=300)
        up    = run(["docker", "compose", "up", "-d"], path, timeout=120)
        ps    = run(["docker", "compose", "ps"], path)
        return f"=== Build ===\n{build}\n\n=== Up ===\n{up}\n\n=== Status ===\n{ps}"

    # ── remote deploy <project> <remote_path> ─────────────────────────────────
    if lower.startswith("remote deploy") and len(parts) >= 4:
        project     = parts[2]
        remote_path = parts[3]
        send(f"⏳ Remote deploying *{project}*...")
        remotes_file = Path.home() / "mcp-dev-server" / "remote_servers.json"
        if not remotes_file.exists():
            return "[No remote servers registered. Use remote_add() in the MCP server first.]"
        remotes = json.loads(remotes_file.read_text())
        if project not in remotes:
            return f"[No remote registered for {project}]"
        cfg      = remotes[project]
        ssh_base = [
            "ssh",
            "-i", cfg["ssh_key_path"],
            "-p", str(cfg["port"]),
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            f"{cfg['user']}@{cfg['host']}",
        ]
        pull    = run(ssh_base + [f"cd {remote_path} && git pull origin main"], timeout=60)
        rebuild = run(ssh_base + [f"cd {remote_path} && docker compose build"], timeout=300)
        up      = run(ssh_base + [f"cd {remote_path} && docker compose up -d"], timeout=120)
        ps      = run(ssh_base + [f"cd {remote_path} && docker compose ps"])
        return f"=== Pull ===\n{pull}\n\n=== Build ===\n{rebuild}\n\n=== Up ===\n{up}\n\n=== Status ===\n{ps}"

    # ── status <project> ──────────────────────────────────────────────────────
    if parts[0].lower() == "status" and len(parts) >= 2:
        return run(["docker", "compose", "ps"], str(PROJECT_ROOT / parts[1]))

    # ── logs <project> <service> [lines] ─────────────────────────────────────
    if parts[0].lower() == "logs" and len(parts) >= 3:
        project = parts[1]
        service = parts[2]
        lines   = str(min(int(parts[3]), 200)) if len(parts) >= 4 and parts[3].isdigit() else "50"
        return run(
            ["docker", "compose", "logs", "--tail", lines, service],
            str(PROJECT_ROOT / project),
        )

    # ── git status <project> ──────────────────────────────────────────────────
    if lower.startswith("git status") and len(parts) >= 3:
        return run(["git", "status", "--short"], str(PROJECT_ROOT / parts[2]))

    # ── git pull <project> ───────────────────────────────────────────────────
    if lower.startswith("git pull") and len(parts) >= 3:
        return run(["git", "pull"], str(PROJECT_ROOT / parts[2]))

    # ── git push <project> <message> ─────────────────────────────────────────
    if lower.startswith("git push") and len(parts) >= 4:
        project = parts[2]
        message = " ".join(parts[3:])
        path    = str(PROJECT_ROOT / project)
        run(["git", "add", "-A"], path)
        commit = run(["git", "commit", "-m", message], path)
        run(["git", "checkout", "-B", "staging"], path)
        push   = run(["git", "push", "origin", "staging", "--force-with-lease"], path, timeout=60)
        return f"{commit}\n{push}\n✅ Pushed to staging. Open a PR to merge to main."

    # ── memory list [prefix] ─────────────────────────────────────────────────
    if lower.startswith("memory list"):
        prefix      = parts[2] if len(parts) >= 3 else ""
        memory_file = Path.home() / "mcp-dev-server" / "memory.json"
        if not memory_file.exists():
            return "[No memory file found]"
        data = json.loads(memory_file.read_text())
        keys = [k for k in data if k.startswith(prefix)]
        if not keys:
            return "[No memory entries found]"
        return "\n".join(f"{k}  ({data[k]['updated']})" for k in sorted(keys))

    # ── memory get <key> ─────────────────────────────────────────────────────
    if lower.startswith("memory get") and len(parts) >= 3:
        key         = parts[2]
        memory_file = Path.home() / "mcp-dev-server" / "memory.json"
        if not memory_file.exists():
            return "[No memory file found]"
        data = json.loads(memory_file.read_text())
        if key not in data:
            return f"[No entry for key: {key}]"
        e = data[key]
        return f"[Updated: {e['updated']}]\n{e['value']}"

    # ── fallback: send to Codex ───────────────────────────────────────────────
    send(f"⏳ Sending to *Codex* on *{MACHINE}*...")
    result = run_agent("codex", text)
    log.info(f"Codex final result: {result!r}")
    return result


# ─── Main polling loop ────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set.")
        sys.exit(1)

    log.info(f"Telegram bot starting on {MACHINE}...")
    send(f"🤖 *{MACHINE}* agent online. Type `help` for commands.")

    offset = 0
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset  = update["update_id"] + 1
                msg     = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text    = msg.get("text", "").strip()

                # Only respond to your own chat
                if chat_id != str(TELEGRAM_CHAT_ID):
                    log.warning(f"Ignoring message from unknown chat_id: {chat_id}")
                    continue

                if not text:
                    continue

                log.info(f"Received: {text!r}")
                try:
                    response = dispatch(text)
                except Exception as e:
                    log.exception(f"Error in dispatch: {e}")
                    response = f"[Error processing command: {e}]"

                if response:
                    send(f"[*{MACHINE}*]\n{response}")
                else:
                    send(f"[*{MACHINE}*] [Empty response from agent]")

        except KeyboardInterrupt:
            log.info("Bot stopped by user.")
            send(f"🔴 *{MACHINE}* agent going offline.")
            break
        except Exception as e:
            log.error(f"Polling error: {e}")

        import time
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
