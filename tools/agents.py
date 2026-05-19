from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from core.audit import audit_event
from core.memory_store import memory_get
from core.permissions import PermissionDenied, check_permission
from core.runtime import PROJECT_ROOT, SERVER_DIR

AGENT_COMMANDS = {
    "kimi": ["kimi", "--quiet", "--afk", "-p"],
    "gemini": ["gemini", "--acp"],
}
AGENTS_DIR = SERVER_DIR / "agents"
AGENT_RUNNER = SERVER_DIR / "core" / "agent_runner.py"
AGENT_TIMEOUT_SECONDS = 90
GEMINI_DISABLED_MESSAGE = (
    "[Gemini temporarily unavailable: ACP integration under repair. "
    "Use kimi for routed tasks until the dedicated Gemini broker is completed.]"
)
ROUTING_GUIDE = """
Agent routing (for Codex orchestration):
  kimi    - large file analysis, frontend/UI, visual tasks, wide codebase scans
  gemini  - temporarily disabled while ACP broker repair is in progress
  codex   - architecture, logic, code generation, debugging (default)
"""
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

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _profile_text(profile: str) -> str:
    path = AGENTS_DIR / f"{profile}.md"
    if not path.exists():
        raise FileNotFoundError(profile)
    return path.read_text(encoding="utf-8")


def _clean_agent_output(text: str) -> str:
    cleaned = _ANSI_RE.sub("", text).replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = []
    skip_prefixes = (
        "Warning: True color",
        "Warning: Basic terminal detected",
        "Warning: 256-color support not detected",
        "To resume this session: kimi -r ",
        "/home/mdb/mcp-dev-server/.venv/lib/python3.12/site-packages/fastmcp/server/auth/providers/jwt.py:",
        "It will be compatible before version 2.0.0.",
        "from authlib.jose import JsonWebKey, JsonWebToken",
    )
    for line in cleaned.splitlines():
        stripped = line.strip()
        if stripped == "Ripgrep is not available. Falling back to GrepTool.":
            continue
        if stripped.startswith(skip_prefixes):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _agent_env(prompt: str) -> dict[str, str]:
    import os

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
    env["AGENT_PROMPT"] = prompt
    return env


def _run_kimi_agent(prompt: str) -> str:
    command = [
        "env",
        "-i",
        *(f"{key}={value}" for key, value in _agent_env(prompt).items()),
        sys.executable,
        str(AGENT_RUNNER),
        "kimi",
        prompt,
    ]
    start = time.time()
    with tempfile.TemporaryFile(mode="w+t") as output_file:
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                stdin=subprocess.DEVNULL,
                stdout=output_file,
                stderr=output_file,
                start_new_session=True,
                text=True,
            )
        except FileNotFoundError:
            audit_event("agent_route_missing", agent="kimi", command=command)
            return f"[Command not found: {command[0]}]"
        except Exception as exc:
            audit_event("agent_route_exception", agent="kimi", command=command, error=str(exc))
            return f"[Error running agent: {exc}]"

        while True:
            returncode = proc.poll()
            if returncode is not None:
                break
            if time.time() - start >= AGENT_TIMEOUT_SECONDS + 5:
                proc.kill()
                audit_event("agent_route_timeout", agent="kimi", command=command)
                return f"[Timed out after {AGENT_TIMEOUT_SECONDS + 5}s: kimi]"
            time.sleep(0.25)

        output_file.seek(0)
        output = _clean_agent_output(output_file.read())
        audit_event(
            "agent_route_result",
            agent="kimi",
            returncode=returncode,
            output_preview=output[:1000],
        )
        return output or f"[No output from kimi; returncode={returncode}]"


def _run_agent(agent: str, prompt: str) -> str:
    if agent == "gemini":
        audit_event(
            "agent_route_disabled",
            agent="gemini",
            reason="acp_broker_repair_pending",
        )
        return GEMINI_DISABLED_MESSAGE
    return _run_kimi_agent(prompt)


def _load_context(namespace: str, context_key: str) -> str:
    if not context_key:
        return ""
    entry = memory_get(namespace, context_key)
    if not entry:
        return ""
    return str(entry.get("value", ""))


def _simple_consensus(task: str, responses: dict[str, str]) -> str:
    normalized = {name: text.lower() for name, text in responses.items()}
    agreements = []
    disagreements = []
    for keyword in ["permission", "path", "audit", "telegram", "remote", "dry-run", "memory"]:
        hits = [name for name, text in normalized.items() if keyword in text]
        if len(hits) > 1:
            agreements.append(f"- Multiple agents mention `{keyword}`: {', '.join(hits)}")
    if not agreements:
        agreements.append("- No strong lexical agreement detected beyond the overall task.")
    lengths = {name: len(text) for name, text in responses.items()}
    if len(set(lengths.values())) > 1:
        disagreements.append("- The responses emphasize different depth/coverage areas.")
    else:
        disagreements.append("- No obvious disagreement detected from a simple lexical pass.")
    return "\n".join([
        "# Consensus Task",
        task,
        "",
        "# Agent Responses",
        "",
        *[f"## {name}\n{text}" for name, text in responses.items()],
        "",
        "# Agreements",
        *agreements,
        "",
        "# Disagreements",
        *disagreements,
        "",
        "# Recommended Next Action",
        "- Implement the overlapping hardening items first, then verify the divergent details with tests.",
    ])


def register(mcp) -> None:
    @mcp.tool()
    def route_task(task: str, agent: str, context_key: str = "", namespace: str = "general", confirm: bool = False) -> str:
        if agent not in AGENT_COMMANDS:
            return f"[Unknown agent '{agent}']\n{ROUTING_GUIDE}"
        try:
            check_permission("agents", tool="route_task", confirm=confirm)
        except PermissionDenied as exc:
            return str(exc)
        context = _load_context(namespace, context_key)
        prompt = task if not context else f"Context ({namespace}:{context_key}):\n{context}\n\n---\n\n{task}"
        audit_event("agent_route", agent=agent, namespace=namespace, context_key=context_key)
        return _run_agent(agent, prompt)

    @mcp.tool()
    def routing_guide() -> str:
        return ROUTING_GUIDE.strip()

    @mcp.tool()
    def agent_profiles() -> str:
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        return "\n".join(sorted(path.stem for path in AGENTS_DIR.glob("*.md")))

    @mcp.tool()
    def route_profiled_task(task: str, profile: str, agent: str = "kimi", context_key: str = "", namespace: str = "general", confirm: bool = False) -> str:
        if agent not in AGENT_COMMANDS:
            return f"[Unknown agent '{agent}']"
        try:
            check_permission("agents", tool="route_profiled_task", confirm=confirm)
            profile_text = _profile_text(profile)
        except PermissionDenied as exc:
            return str(exc)
        except FileNotFoundError:
            return f"[Unknown profile: {profile}]"
        context = _load_context(namespace, context_key)
        prompt = f"{profile_text}\n\nTask:\n{task}"
        if context:
            prompt = f"Context ({namespace}:{context_key}):\n{context}\n\n---\n\n{prompt}"
        audit_event("agent_route_profile", agent=agent, profile=profile, namespace=namespace, context_key=context_key)
        return _run_agent(agent, prompt)

    @mcp.tool()
    def consensus_task(task: str, agents_csv: str = "kimi,gemini", context_key: str = "", namespace: str = "general", confirm: bool = False) -> str:
        try:
            check_permission("agents", tool="consensus_task", confirm=confirm)
        except PermissionDenied as exc:
            return str(exc)
        context = _load_context(namespace, context_key)
        prompt = task if not context else f"Context ({namespace}:{context_key}):\n{context}\n\n---\n\n{task}"
        selected = [item.strip() for item in agents_csv.split(",") if item.strip() in AGENT_COMMANDS]
        responses = {}
        for agent in selected:
            audit_event("agent_consensus_call", agent=agent, namespace=namespace, context_key=context_key)
            responses[agent] = _run_agent(agent, prompt)
        return _simple_consensus(task, responses)
