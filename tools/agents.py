from __future__ import annotations

from core.runtime import load_memory, run_safe

AGENT_COMMANDS = {
    "kimi": ["kimi", "--quiet", "--afk", "-p"],
    "gemini": ["gemini", "--"],
}

ROUTING_GUIDE = """
Agent routing (for Codex orchestration):
  kimi    - large file analysis, frontend/UI, visual tasks, wide codebase scans
  gemini  - web research, documentation, 1M+ token context tasks
  codex   - architecture, logic, code generation, debugging (default)

Efficient delegation workflow:
  1. task_start(project, task)          - load all context in one call
  2. memory_get(key)                    - load specific prior findings
  3. route_task(task, agent, key)       - delegate with context
  4. memory_set(key, result)            - store result for next agent
  5. telegram_notify(msg)               - report completion
"""


def register(mcp) -> None:
    @mcp.tool()
    def route_task(task: str, agent: str, context_key: str = "") -> str:
        """
        Delegate a task to Kimi or Gemini CLI.
        context_key: memory key prepended as context.
        """
        if agent not in AGENT_COMMANDS:
            return f"[Unknown agent '{agent}']\n{ROUTING_GUIDE}"
        prompt = task
        if context_key:
            data = load_memory()
            if context_key in data:
                prompt = f"Context ({context_key}):\n{data[context_key]['value']}\n\n---\n\n{task}"
        return run_safe(AGENT_COMMANDS[agent] + [prompt], label=f"{agent} response", timeout=300)

    @mcp.tool()
    def routing_guide() -> str:
        """Return the agent routing and orchestration guide."""
        return ROUTING_GUIDE.strip()
