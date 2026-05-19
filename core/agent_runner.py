from __future__ import annotations

import asyncio
import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SERVER_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = Path.home() / "workspaces"
AGENT_TIMEOUT_SECONDS = 90
GEMINI_ACP_TIMEOUT_SECONDS = 20


PASSTHROUGH_ENV_KEYS = [
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "USER",
    "SHELL",
    "XDG_RUNTIME_DIR",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "DBUS_SESSION_BUS_ADDRESS",
    "SSH_AUTH_SOCK",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
]


def _tool_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in PASSTHROUGH_ENV_KEYS if os.environ.get(key)}
    env["PATH"] = (
        f"{SERVER_DIR / '.venv' / 'bin'}:"
        "/home/mdb/.local/bin:"
        "/home/mdb/.cargo/bin:"
        "/home/mdb/.npm-global/bin:"
        "/usr/local/bin:/usr/bin:/bin:"
        + os.environ.get("PATH", "")
    )
    env["TERM"] = "dumb"
    env["NO_COLOR"] = "1"
    env["CLICOLOR"] = "0"
    env["FORCE_COLOR"] = "0"
    env["CI"] = "1"
    env["PYTHONWARNINGS"] = "ignore"
    env["GEMINI_CLI_NO_RELAUNCH"] = "1"
    return env


def _read_jsonrpc_until(proc: subprocess.Popen[str], target_id: int, chunks: list[str], deadline: float) -> dict[str, Any]:
    selector = selectors.DefaultSelector()
    assert proc.stdout is not None
    assert proc.stderr is not None
    selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
    selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
    stderr_lines: list[str] = []

    while True:
        if proc.poll() is not None and not selector.get_map():
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Gemini ACP timed out waiting for response id {target_id}")
        events = selector.select(timeout=1)
        if not events:
            continue
        for key, _ in events:
            stream_name = key.data
            line = key.fileobj.readline()
            if not line:
                selector.unregister(key.fileobj)
                continue
            if stream_name == "stderr":
                stderr_lines.append(line.rstrip())
                continue
            line = line.strip()
            if not line:
                continue
            message = json.loads(line)
            if message.get("method") == "session/update":
                update = (message.get("params") or {}).get("update") or {}
                if update.get("sessionUpdate") == "agent_message_chunk":
                    content = update.get("content") or {}
                    if content.get("type") == "text" and content.get("text"):
                        chunks.append(str(content["text"]))
                continue
            if message.get("id") == target_id:
                if "error" in message:
                    error = message["error"]
                    detail = error.get("message") or json.dumps(error, ensure_ascii=False)
                    raise RuntimeError(detail)
                return message

    stderr_text = "\n".join(stderr_lines).strip()
    raise RuntimeError(stderr_text or "Gemini ACP exited before returning a response")



def _send_jsonrpc(proc: subprocess.Popen[str], payload: dict[str, Any]) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()



def _run_gemini_acp(prompt: str) -> str:
    proc = subprocess.Popen(
        ["gemini", "--acp", "--approval-mode", "yolo"],
        cwd=str(PROJECT_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=_tool_env(),
        start_new_session=True,
    )

    try:
        chunks: list[str] = []
        deadline = time.monotonic() + GEMINI_ACP_TIMEOUT_SECONDS
        _send_jsonrpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "auth": {"terminal": False},
                        "fs": {"readTextFile": False, "writeTextFile": False},
                        "terminal": False,
                    },
                    "clientInfo": {"name": "mcp-dev-server", "version": "1.0"},
                },
            },
        )
        _read_jsonrpc_until(proc, 1, chunks, deadline)

        _send_jsonrpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/new",
                "params": {"cwd": str(PROJECT_ROOT), "mcpServers": []},
            },
        )
        new_session = _read_jsonrpc_until(proc, 2, chunks, deadline)
        session_id = new_session["result"]["sessionId"]

        _send_jsonrpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": prompt}],
                },
            },
        )
        _read_jsonrpc_until(proc, 3, chunks, deadline)
        return "".join(chunks).strip() or "[No output from gemini]"
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            if proc.stdin is not None:
                proc.stdin.close()
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()


def _run_gemini_headless(prompt: str) -> str:
    result = subprocess.run(
        ["gemini", "--approval-mode", "yolo", "-p", prompt, "--output-format", "text"],
        cwd=str(PROJECT_ROOT),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=AGENT_TIMEOUT_SECONDS,
        env=_tool_env(),
    )
    output = (result.stdout or "").strip()
    if not output and result.stderr:
        output = result.stderr.strip()
    return output or "[No output from gemini]"


async def _run_kimi_sdk_async(prompt: str) -> str:
    from kimi_agent_sdk import prompt as kimi_prompt

    messages: list[str] = []
    async for message in kimi_prompt(
        prompt,
        work_dir=None,
        yolo=True,
        final_message_only=True,
    ):
        text = message.extract_text()
        if text:
            messages.append(text)
    return "".join(messages).strip() or "[No output from kimi]"



def _run_kimi_sdk(prompt: str) -> str:
    return asyncio.run(_run_kimi_sdk_async(prompt))



def main() -> int:
    if len(sys.argv) != 3:
        print("[Usage: agent_runner.py <agent> <prompt>]")
        return 2

    agent, prompt = sys.argv[1], sys.argv[2]
    try:
        if agent == "gemini":
            try:
                print(_run_gemini_acp(prompt))
            except Exception:
                print(_run_gemini_headless(prompt))
            return 0
        if agent == "kimi":
            print(_run_kimi_sdk(prompt))
            return 0
        print(f"[Unknown agent: {agent}]")
        return 2
    except subprocess.TimeoutExpired:
        print(f"[Timed out after {AGENT_TIMEOUT_SECONDS}s: {agent}]")
        return 124
    except Exception as exc:
        print(f"[Error running {agent}: {exc}]")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
