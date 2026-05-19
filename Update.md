# devMCP Hardening and Upgrade Instructions for Codex

## Mission

Bring this repository up to a safer, cleaner, production-grade internal tool standard without removing the current core value: devMCP must remain a local AI DevOps/control-plane MCP server with Telegram control, agent delegation, project tooling, memory, remote deployment helpers, and workflow skills.

This file is written for Codex. Execute it as an implementation brief. Do not ask the user to clarify anything unless the repository cannot run at all. Make sensible decisions, patch the code, run tests/checks, and report exactly what changed.

## Non-negotiable rules

1. Do not rewrite the whole project.
2. Do not remove existing public tool names unless a replacement compatibility wrapper remains.
3. Do not leave dangerous behavior enabled by default.
4. Do not use placeholder code.
5. Do not add pseudo-code.
6. Do not add TODO-only implementations.
7. Do not add external services.
8. Keep dependencies minimal and standard-library-first.
9. Preserve the modular layout: `core/`, `tools/`, `skills/`, `server.py`, `registry.py`, `telegram_bot.py`.
10. Treat `server_monolith.py` as legacy/reference code. Do not make it the main implementation. Either update its security warnings or mark it deprecated in the README.

## Current repo facts to account for

The current codebase contains:

- `server.py` as the modular FastMCP entry point.
- `registry.py` loading modules from `tools/` and `skills/`.
- `core/runtime.py` with shared constants, JSON helpers, subprocess execution, tool installation, and Telegram send helper.
- `tools/files.py` with file read/write/cache/search tools.
- `tools/remote.py` with remote server registration and SSH-based remote operations.
- `tools/memory.py` with one global JSON memory file.
- `tools/agents.py` with Kimi/Gemini delegation.
- `tools/git.py` with Git operations including push-to-staging.
- `tools/docker.py` with Docker Compose operations and local deploy.
- `telegram_bot.py` with command parsing and Codex/Kimi/Gemini delegation.

The main risks that must be fixed are:

- `remote_exec(project, command)` allows unrestricted arbitrary shell execution over SSH.
- SSH currently uses `StrictHostKeyChecking=no`.
- Telegram fallback sends arbitrary text to Codex.
- Telegram Codex command uses `--dangerously-bypass-approvals-and-sandbox`.
- Project path handling allows unsafe path construction.
- `write_file()` can write outside intended project roots if path traversal is used.
- `git_clone(repo_url, project_name)` can clone into unsafe paths if `project_name` is malicious.
- `ensure_tools()` silently installs system/global packages.
- Memory is one global JSON file, without locking, expiry, namespaces, or redaction.
- Logs/Telegram/memory can leak secrets.
- There is no audit trail for tool calls.
- There is no dry-run support for dangerous operations.
- There is no central permission policy.

## Required final behavior

After this work:

- The MCP server must still start from `server.py`.
- Existing read-only tools must still work.
- Dangerous tools must be gated by a permission policy.
- File paths must be constrained to allowed roots.
- Remote execution must no longer accept arbitrary shell by default.
- Telegram must not silently run unknown messages through Codex.
- Codex must not run with `--dangerously-bypass-approvals-and-sandbox` by default.
- Every tool execution path must be auditable.
- Secrets must be redacted before being logged, sent to Telegram, or stored in memory.
- Memory must support namespaces while preserving compatibility with existing `memory_set`, `memory_get`, `memory_list`, and `memory_delete` tools.
- Deploy/write/remote/git-push operations must support dry-run mode.
- README must clearly document security behavior.

---

# Phase 1: Add core safety modules

Create these new files:

```text
core/security.py
core/audit.py
core/permissions.py
core/paths.py
core/remote_actions.py
core/memory_store.py
```

## 1.1 Implement `core/security.py`

Implement production code with these functions:

```python
from __future__ import annotations

import re
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"(?i)(aws_access_key_id\s*[=:]\s*)([A-Z0-9]{16,})"),
    re.compile(r"(?i)(aws_secret_access_key\s*[=:]\s*)([A-Za-z0-9/+=]{20,})"),
    re.compile(r"(?i)(openai_api_key\s*[=:]\s*)(sk-[A-Za-z0-9_\-]{20,})"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)(['\"]?[^'\"\s]{12,}['\"]?)"),
    re.compile(r"(?i)(secret\s*[=:]\s*)(['\"]?[^'\"\s]{12,}['\"]?)"),
    re.compile(r"(?i)(token\s*[=:]\s*)(['\"]?[^'\"\s]{12,}['\"]?)"),
    re.compile(r"(?i)(password\s*[=:]\s*)(['\"]?[^'\"\s]{8,}['\"]?)"),
    re.compile(r"(?i)(passwd\s*[=:]\s*)(['\"]?[^'\"\s]{8,}['\"]?)"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)([A-Za-z0-9._\-]{12,})"),
    re.compile(r"(?i)(x-api-key:\s*)([A-Za-z0-9._\-]{12,})"),
]

SENSITIVE_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.prod",
    "id_rsa",
    "id_ed25519",
    "known_hosts",
}


def redact_text(value: str) -> str:
    text = str(value)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}***REDACTED***", text)
    return text


def redact_obj(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_obj(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_obj(item) for item in value)
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_s = str(key)
            if re.search(r"(?i)(password|passwd|token|secret|api[_-]?key|authorization|private[_-]?key)", key_s):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = redact_obj(item)
        return redacted
    return value


def is_sensitive_path(path: str) -> bool:
    normalized = str(path).replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if name in SENSITIVE_FILENAMES:
        return True
    if normalized.endswith("/.ssh/config"):
        return True
    if "/.ssh/" in normalized:
        return True
    return False
```

Use this module everywhere output leaves the process:

- `run_safe()` return values
- `telegram_send()`
- Telegram bot `send()`
- audit logs
- memory writes
- remote command outputs

## 1.2 Implement `core/audit.py`

Implement JSONL audit logging.

Requirements:

- File path: `~/mcp-dev-server/logs/audit.jsonl`
- Directory must be created automatically.
- Each event must be one JSON object per line.
- Use redaction before writing.
- Use a simple lock file or atomic append approach.
- Do not fail the main tool execution if audit logging fails.

Required functions:

```python
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from core.runtime import SERVER_DIR
from core.security import redact_obj

AUDIT_DIR = SERVER_DIR / "logs"
AUDIT_FILE = AUDIT_DIR / "audit.jsonl"


def new_run_id() -> str:
    return str(uuid.uuid4())


def audit_event(event_type: str, **fields: Any) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event_type": event_type,
        **fields,
    }
    safe_event = redact_obj(event)
    line = json.dumps(safe_event, sort_keys=True, ensure_ascii=False)
    try:
        with AUDIT_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        return
```

Then integrate it into:

- `core.runtime.run_safe()`
- file write operations
- git pull/push/clone operations
- docker build/restart/deploy operations
- remote actions
- memory set/delete
- Telegram dispatch
- agent routing

Every audit event must include:

- `tool` where known
- `project` where known
- `action`
- `status`
- `duration_ms` where practical

## 1.3 Implement `core/permissions.py`

Implement a central permission policy.

Use config file:

```text
~/mcp-dev-server/permissions.json
```

If the file does not exist, create it with this default policy:

```json
{
  "read": "allow",
  "write": "prompt",
  "git": "allow",
  "docker": "prompt",
  "deploy": "prompt",
  "remote": "prompt",
  "dangerous": "deny",
  "network": "allow",
  "database": "prompt",
  "agents": "allow",
  "install": "deny",
  "telegram_codex_fallback": "deny"
}
```

Supported policy values:

- `allow`
- `prompt`
- `deny`

Because MCP tools and the Telegram bot may not have an interactive prompt, treat `prompt` as deny unless the tool call contains `confirm=True`.

Implement:

```python
class PermissionDenied(RuntimeError):
    pass


def load_policy() -> dict[str, str]:
    ...


def check_permission(permission: str, *, tool: str, confirm: bool = False) -> None:
    ...
```

Behavior:

- `allow`: pass
- `deny`: raise `PermissionDenied`
- `prompt` and `confirm=False`: raise `PermissionDenied` with a message telling the caller to retry with `confirm=True`
- `prompt` and `confirm=True`: pass

All dangerous tools must catch `PermissionDenied` and return a clear string error.

## 1.4 Implement `core/paths.py`

Implement safe path resolution.

Requirements:

- All project paths must live under `PROJECT_ROOT`.
- `project` must be a simple directory name or a safe relative path under `PROJECT_ROOT`.
- Reject absolute paths in project names and file paths.
- Reject `..` traversal.
- Resolve symlinks and reject paths that escape the allowed root.
- Reject sensitive paths by default when writing or sending contents.

Implement:

```python
from __future__ import annotations

from pathlib import Path

from core.runtime import PROJECT_ROOT
from core.security import is_sensitive_path

class UnsafePathError(ValueError):
    pass


def safe_project_path(project: str) -> Path:
    ...


def safe_project_file(project: str, file_path: str, *, must_exist: bool = False, allow_sensitive: bool = False) -> Path:
    ...


def safe_project_cwd(project: str) -> str:
    return str(safe_project_path(project))


def safe_new_project_name(project_name: str) -> str:
    ...
```

Rules:

- `safe_new_project_name("foo")` returns `foo`.
- `safe_new_project_name("../foo")` raises `UnsafePathError`.
- `safe_project_file("app", "src/main.py")` returns a resolved path under `~/workspaces/app`.
- `safe_project_file("app", "../../.ssh/id_rsa")` raises.
- `safe_project_file("app", ".env")` raises unless `allow_sensitive=True`.

## 1.5 Implement `core/remote_actions.py`

Replace raw remote execution with allowlisted actions.

Implement:

```python
from __future__ import annotations

import shlex
from typing import Any

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


def build_remote_command(action: str, *, remote_path: str = "", service: str = "", branch: str = "main", lines: int = 50, log_path: str = "") -> str:
    ...
```

Security requirements:

- Use `shlex.quote()` for all remote arguments.
- Validate `action` against `ALLOWED_REMOTE_ACTIONS`.
- Reject `remote_path` that is empty for actions requiring a project directory.
- Limit `lines` to max 200.
- For `tail_log`, require an absolute path under `/var/log/` or a path under the provided remote project directory.
- Do not allow semicolons, backticks, `$()`, pipes, redirects, or `&&` from user-controlled fields.
- Compose commands internally, not by accepting raw shell text.

Required commands:

- `system_info`: `uname -a && uptime`
- `disk_usage`: `df -h`
- `memory_usage`: `free -h`
- `docker_ps`: `cd <remote_path> && docker compose ps`
- `docker_logs`: `cd <remote_path> && docker compose logs --tail <lines> <service>`
- `docker_build`: `cd <remote_path> && docker compose build [service]`
- `docker_up`: `cd <remote_path> && docker compose up -d [service]`
- `docker_restart`: `cd <remote_path> && docker compose restart [service]`
- `git_status`: `cd <remote_path> && git status --short`
- `git_pull`: `cd <remote_path> && git fetch origin && git checkout <branch> && git pull origin <branch>`
- `service_status`: `systemctl status <service> --no-pager`
- `service_restart`: `sudo systemctl restart <service>`

---

# Phase 2: Update `core/runtime.py`

Modify `core/runtime.py` instead of duplicating command helpers elsewhere.

## 2.1 Redact command output

Import:

```python
from core.security import redact_text, redact_obj
from core.audit import audit_event, new_run_id
```

Modify `trim()` so it redacts returned text before returning.

Modify `run_safe()` so it:

- creates a `run_id`
- records start time
- runs the command
- redacts stdout/stderr
- audits command execution
- includes command, cwd, label, status, duration
- does not audit full huge output; audit only first 1000 redacted chars
- returns redacted trimmed output

Do not log raw secrets.

## 2.2 Disable automatic installs by default

Change `ensure_tools()` so it never installs packages unless explicitly enabled.

Add environment variable:

```text
DEVMCP_AUTO_INSTALL=1
```

Behavior:

- If `DEVMCP_AUTO_INSTALL` is not `1`, only record missing tools and return.
- Do not call `apt_install`, `pip_install`, `npm_global`, or `cargo install` unless auto-install is enabled.
- If auto-install is enabled, require permission `install` with `confirm=True` internally only if policy allows it.
- If install permission is denied, record missing tools in `tools_installed.json` as `missing`.

Update startup behavior in `server.py` to not swallow all exceptions silently. Replace bare `except Exception: pass` with audit logging and a safe warning.

## 2.3 Harden Telegram send

Modify `telegram_send()` to redact messages before sending.

Do not use Markdown parse mode unless messages are escaped or known safe. The simplest fix is to remove `parse_mode=Markdown` from `telegram_send()` to prevent formatting/injection issues.

---

# Phase 3: Update `tools/files.py`

Replace all direct path joins with `core.paths` helpers.

## 3.1 Required changes

- Import `safe_project_file`, `safe_project_path`, and `UnsafePathError`.
- Use `safe_project_file()` in:
  - `_get_mtime()`
  - `read_project_file()`
  - `write_project_file()`
  - `file_outline()`
- Use `safe_project_path()` in `search_files()`.
- Catch `UnsafePathError` and return `[Unsafe path: <message>]`.
- For reads of sensitive files, return an explicit refusal unless the caller passes `allow_sensitive=True`.

Change the MCP `read_file` signature to:

```python
def read_file(project: str, file_path: str, start_line: int = 1, end_line: int = 0, allow_sensitive: bool = False) -> str:
```

Change `read_project_file()` accordingly.

Change the MCP `write_file` signature to:

```python
def write_file(project: str, file_path: str, content: str, confirm: bool = False, dry_run: bool = False) -> str:
```

Before writing:

- call `check_permission("write", tool="write_file", confirm=confirm)`
- if `dry_run=True`, do not write; return exactly what file would be written and line/char counts
- audit the operation
- redact content in audit logs

Keep compatibility by allowing existing calls without `confirm`; they should now return a clear permission message if policy says prompt.

## 3.2 Cache safety

Cache keys must be based on the resolved safe path, not raw user input.

Do not cache sensitive files.

---

# Phase 4: Update `tools/remote.py`

## 4.1 Remove unrestricted remote shell by default

Keep a tool named `remote_exec` for compatibility, but change its behavior.

New signature:

```python
def remote_exec(project: str, action: str, remote_path: str = "", service: str = "", branch: str = "main", lines: int = 50, log_path: str = "", confirm: bool = False, dry_run: bool = False) -> str:
```

Behavior:

- Treat the second argument as an allowlisted action, not a raw shell command.
- Call `check_permission("remote", tool="remote_exec", confirm=confirm)`.
- If action is deploy/build/restart/service_restart, also call the relevant `deploy` or `dangerous` permission.
- Build the command using `core.remote_actions.build_remote_command()`.
- If `dry_run=True`, return the exact redacted SSH target and command that would run, but do not execute it.
- Audit the operation.

Do not accept arbitrary shell commands unless config explicitly enables it.

Add `~/mcp-dev-server/config.json` support with:

```json
{
  "allow_raw_remote_shell": false,
  "allow_telegram_codex_fallback": false,
  "allow_codex_dangerous_bypass": false
}
```

If `allow_raw_remote_shell` is true, expose a separate tool:

```python
def remote_raw_shell(project: str, command: str, confirm: bool = False, dry_run: bool = False) -> str:
```

This tool must require both:

- `remote`
- `dangerous`

Default policy denies `dangerous`, so it must not work unless the user intentionally changes policy.

## 4.2 Harden SSH options

Replace:

```text
StrictHostKeyChecking=no
```

with:

```text
StrictHostKeyChecking=accept-new
```

Also add:

```text
IdentitiesOnly=yes
```

Validate remote config before use:

- host cannot be empty
- user cannot be empty
- port must be 1–65535
- ssh key path must exist

## 4.3 Update remote helper tools

Update these tools to use the new action builder and permission checks:

- `remote_git_pull()`
- `remote_rebuild()`
- `remote_logs()`
- `remote_deploy()`

Add `confirm` and `dry_run` parameters where appropriate.

Required signatures:

```python
def remote_git_pull(project: str, remote_path: str, branch: str = "main", confirm: bool = False, dry_run: bool = False) -> str

def remote_rebuild(project: str, remote_path: str, service: str = "", confirm: bool = False, dry_run: bool = False) -> str

def remote_logs(project: str, remote_path: str, service: str, lines: int = 50) -> str

def remote_deploy(project: str, remote_path: str, branch: str = "main", service: str = "", confirm: bool = False, dry_run: bool = False) -> str
```

`remote_logs()` is read-only and should not require confirmation, but still requires `remote` permission.

`remote_deploy()` must require:

- `remote`
- `deploy`

---

# Phase 5: Update `tools/git.py`

## 5.1 Safe project paths

Replace all `str(PROJECT_ROOT / project)` with `safe_project_cwd(project)`.

Wrap unsafe path errors.

## 5.2 Harden `git_clone`

Change signature:

```python
def git_clone(repo_url: str, project_name: str, confirm: bool = False, dry_run: bool = False) -> str:
```

Requirements:

- Validate `project_name` with `safe_new_project_name()`.
- Require `write` permission.
- Reject repo URLs that are not `https://`, `git@`, or `ssh://`.
- If `dry_run=True`, do not clone; return target path and command.
- Audit clone.

## 5.3 Harden `git_pull`

Change signature:

```python
def git_pull(project: str, confirm: bool = False, dry_run: bool = False) -> str:
```

Require `git` permission. If policy says allow, it works. If changed to prompt, require confirm.

## 5.4 Harden `git_push_staging`

Change signature:

```python
def git_push_staging(project: str, commit_message: str, pr_description: str = "", confirm: bool = False, dry_run: bool = False) -> str:
```

Requirements:

- Require `git` and `write` permissions.
- Reject empty commit messages.
- If `dry_run=True`, return the commands that would run.
- Audit add/commit/checkout/push.
- Redact Telegram message.

---

# Phase 6: Update `tools/docker.py`

## 6.1 Safe project paths

Use `safe_project_cwd(project)` and `safe_project_file(project, "docker-compose.yml")`.

## 6.2 Add permissions and dry-runs

Change signatures:

```python
def docker_compose_build(project: str, service: str = "", confirm: bool = False, dry_run: bool = False) -> str

def docker_compose_restart(project: str, service: str = "", confirm: bool = False, dry_run: bool = False) -> str

def deploy_local(project: str, service: str = "", run_tests_first: bool = False, confirm: bool = False, dry_run: bool = False) -> str
```

Requirements:

- `docker_compose_ps()` and `docker_compose_logs()` require no confirmation, but use safe paths.
- Build/restart require `docker` permission.
- Deploy requires `docker` and `deploy` permissions.
- `dry_run=True` returns planned commands and does not execute.
- Audit all operations.

---

# Phase 7: Update `tools/memory.py`

Replace direct use of `load_memory()` and `save_memory()` with a new namespaced memory store.

## 7.1 Implement `core/memory_store.py`

Use directory:

```text
~/mcp-dev-server/memory/
```

Each namespace is its own JSON file:

```text
general.json
hostflow.json
storagezen.json
devmcp.json
```

Required functions:

```python
def normalize_namespace(namespace: str) -> str

def memory_set(namespace: str, key: str, value: str, ttl_seconds: int = 0) -> None

def memory_get(namespace: str, key: str) -> dict | None

def memory_list(namespace: str = "general", prefix: str = "") -> list[tuple[str, dict]]

def memory_delete(namespace: str, key: str) -> bool

def memory_search(namespace: str, query: str) -> list[tuple[str, dict]]
```

Data shape:

```json
{
  "key": {
    "value": "...",
    "updated": "2026-05-19T00:00:00+0200",
    "expires": null
  }
}
```

Requirements:

- Redact values before writing.
- Use atomic writes: write temp file, then replace.
- Remove expired entries on read/list/search.
- Namespace must be safe filename only: lowercase letters, numbers, underscore, dash.
- If the old `~/mcp-dev-server/memory.json` exists, migrate its keys into `memory/general.json` once, preserving values.
- Write a marker file `memory/.migration_done` after migration.

## 7.2 Update MCP memory tools

Keep existing tools compatible:

```python
def memory_set(key: str, value: str, namespace: str = "general", ttl_seconds: int = 0) -> str

def memory_get(key: str, namespace: str = "general") -> str

def memory_list(prefix: str = "", namespace: str = "general") -> str

def memory_delete(key: str, namespace: str = "general") -> str
```

Add:

```python
def memory_search(query: str, namespace: str = "general") -> str
```

Audit set/delete/search operations.

---

# Phase 8: Update `tools/agents.py`

## 8.1 Use namespaced memory

Change `route_task()` signature:

```python
def route_task(task: str, agent: str, context_key: str = "", namespace: str = "general", confirm: bool = False) -> str
```

Requirements:

- Require `agents` permission.
- Retrieve context from namespaced memory.
- Redact prompt in audit logs.
- Audit agent, duration, status.

## 8.2 Add agent profiles

Create directory:

```text
agents/
```

Create these files:

```text
agents/linux_admin.md
agents/security_auditor.md
agents/code_reviewer.md
agents/product_manager.md
agents/documentation_writer.md
agents/devops_deployer.md
```

Each profile must contain:

- role
- strengths
- boundaries
- preferred tools
- output format

Add tool:

```python
def agent_profiles() -> str
```

Return available profile names.

Add tool:

```python
def route_profiled_task(task: str, profile: str, agent: str = "kimi", context_key: str = "", namespace: str = "general", confirm: bool = False) -> str
```

This must prepend the profile instructions to the prompt.

## 8.3 Add consensus tool

Add:

```python
def consensus_task(task: str, agents_csv: str = "kimi,gemini", context_key: str = "", namespace: str = "general", confirm: bool = False) -> str
```

Requirements:

- Split agents by comma.
- Run only known agents.
- Collect responses.
- Return sections:
  - `# Consensus Task`
  - `# Agent Responses`
  - `# Agreements`
  - `# Disagreements`
  - `# Recommended Next Action`
- The agreements/disagreements can be generated by a local deterministic comparison initially: identify repeated keywords/phrases and summarize conservatively. Do not invent certainty.
- Audit all agent calls.

---

# Phase 9: Harden `telegram_bot.py`

## 9.1 Remove dangerous Codex default

Change Codex command construction.

Current behavior includes:

```text
--dangerously-bypass-approvals-and-sandbox
```

Remove that flag by default.

Only allow it if config file `~/mcp-dev-server/config.json` contains:

```json
{
  "allow_codex_dangerous_bypass": true
}
```

Even then, require Telegram command prefix:

```text
codex-danger: <prompt>
```

Do not use dangerous bypass for normal `codex:`.

## 9.2 Disable unknown-message Codex fallback

Current behavior sends anything unknown to Codex.

Replace fallback with:

```text
[Unknown command. Type help. To send to Codex, use codex: <prompt>.]
```

Only restore old fallback if config contains:

```json
{
  "allow_telegram_codex_fallback": true
}
```

Default must be false.

## 9.3 Apply path safety and permissions

For Telegram commands:

- `deploy <project>` must require deploy permission and confirmation.
- Since Telegram is non-interactive, require explicit command syntax:
  - `deploy <project> --confirm`
  - `remote deploy <project> <path> --confirm`
  - `git push <project> <message> --confirm`
- Without `--confirm`, return a refusal explaining the exact command to retry.

Use `safe_project_cwd()` for project paths.

Use `StrictHostKeyChecking=accept-new` for SSH.

Redact all outbound messages.

Remove Markdown parse mode from Telegram sends or safely escape content.

Audit every Telegram command:

- received command class
- accepted/rejected
- machine hostname
- chat_id redacted or hashed

## 9.4 Harden memory commands

Update Telegram memory commands to use namespaced memory store.

Support:

```text
memory list [namespace] [prefix]
memory get <namespace> <key>
```

Preserve old `memory get <key>` by mapping it to namespace `general`.

---

# Phase 10: Add workflow runner

Create:

```text
core/workflow_runner.py
workflows/
workflows/deploy_check.json
workflows/ci_debug.json
workflows/pr_review.json
workflows/incident_triage.json
```

Use JSON, not YAML, to avoid adding dependencies.

## 10.1 Workflow schema

Workflow files must use this shape:

```json
{
  "name": "deploy_check",
  "description": "Check project before deploy",
  "steps": [
    {"tool": "git_status", "args": {}},
    {"tool": "docker_compose_ps", "args": {}},
    {"tool": "run_tests", "args": {"test_command": "pytest"}}
  ]
}
```

## 10.2 Runner behavior

Implement:

```python
def list_workflows() -> list[str]

def load_workflow(name: str) -> dict

def run_workflow(name: str, project: str, dry_run: bool = True, confirm: bool = False) -> str
```

Requirements:

- Default `dry_run=True`.
- Do not execute unknown tools.
- Use an internal allowlist mapping workflow tool names to Python callables or safe command wrappers.
- Audit workflow start/end/step result.
- Return a markdown report.

## 10.3 Expose MCP tools

Create or update `skills/workflows.py` to expose:

```python
def workflow_list() -> str

def workflow_run(name: str, project: str, dry_run: bool = True, confirm: bool = False) -> str
```

---

# Phase 11: Add task queue

Create:

```text
core/tasks.py
```

Use SQLite database:

```text
~/mcp-dev-server/tasks.sqlite3
```

Schema:

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    agent TEXT,
    project TEXT,
    namespace TEXT,
    prompt TEXT NOT NULL,
    result TEXT,
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
```

Statuses:

- `pending`
- `running`
- `complete`
- `failed`

Implement:

```python
def task_create(title: str, prompt: str, project: str = "", agent: str = "", namespace: str = "general") -> str

def task_list(status: str = "") -> list[dict]

def task_get(task_id: str) -> dict | None

def task_update(task_id: str, status: str, result: str = "") -> bool
```

Create MCP tools in a new file:

```text
tools/tasks.py
```

Expose:

```python
def task_create(title: str, prompt: str, project: str = "", agent: str = "", namespace: str = "general") -> str

def task_list(status: str = "") -> str

def task_get(task_id: str) -> str

def task_complete(task_id: str, result: str) -> str

def task_fail(task_id: str, result: str) -> str
```

Add `tools.tasks` to `registry.py`.

Redact prompts/results in audit logs, but store redacted values in DB to prevent secret persistence.

---

# Phase 12: Update other tools for safe paths

Update all tools that use `PROJECT_ROOT / project` or accept a project file path.

Files to inspect and patch:

```text
tools/database.py
tools/http_config.py
tools/javascript_dev.py
tools/offline_code.py
tools/python_dev.py
tools/quality.py
tools/security.py
skills/ops_workflows.py
skills/project_health.py
skills/scaffold.py
skills/workflows.py
```

Required rules:

- Use `safe_project_cwd(project)` for cwd.
- Use `safe_project_file(project, file_path)` for files.
- Use `safe_project_path(project)` for project directory access.
- Catch `UnsafePathError` and return a safe error.
- Any operation that writes files requires `write` permission and `confirm=True` if policy says prompt.
- Any operation that runs install commands requires `install` permission and must default to denied.
- Any operation that deploys, restarts services, modifies database, restores database, or writes config requires confirmation and audit.

Special handling:

- `tools/database.py`: database restore must require `database` and `dangerous` or at least `database` plus `confirm=True`.
- `tools/quality.py`: formatters that modify files require `write` permission.
- `tools/security.py`: scanners are read-only unless they install tools.
- `tools/http_config.py`: HTTP requests can stay allowed under `network` permission.
- `skills/scaffold.py`: project/file creation requires `write` permission and dry-run support.

---

# Phase 13: Add health and diagnostics

Create:

```text
tools/health.py
```

Expose:

```python
def devmcp_health() -> str
```

It must report:

- server directory
- project root
- memory directory status
- audit log status
- permissions policy path and loaded status
- remote count
- known tools/modules count
- Telegram configured yes/no
- auto-install enabled yes/no
- missing common tools from `tools_installed.json`

Add `tools.health` to `registry.py`.

Do not reveal tokens or secrets.

---

# Phase 14: Documentation updates

Update `README.md` with these sections:

1. What devMCP is
2. Security model
3. Permission policy
4. Safe paths
5. Remote execution model
6. Telegram bot safety
7. Memory namespaces
8. Audit logs
9. Dry-run and confirmation usage
10. Auto-install behavior
11. Agent profiles and consensus mode
12. Workflows
13. Task queue

Add an explicit warning near the top:

```text
Security warning: devMCP can read files, write files, run development commands, control Docker, and perform remote SSH operations. Do not expose it publicly. Run it only on trusted machines and networks. Dangerous operations are denied or confirmation-gated by default.
```

Update `.env.example` with:

```text
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=
DEVMCP_AUTO_INSTALL=0
```

Add sample config files:

```text
examples/config.json
examples/permissions.json
```

`examples/config.json`:

```json
{
  "allow_raw_remote_shell": false,
  "allow_telegram_codex_fallback": false,
  "allow_codex_dangerous_bypass": false
}
```

`examples/permissions.json`:

```json
{
  "read": "allow",
  "write": "prompt",
  "git": "allow",
  "docker": "prompt",
  "deploy": "prompt",
  "remote": "prompt",
  "dangerous": "deny",
  "network": "allow",
  "database": "prompt",
  "agents": "allow",
  "install": "deny",
  "telegram_codex_fallback": "deny"
}
```

---

# Phase 15: Test requirements

Create a minimal test suite if none exists.

Use `pytest`.

Create:

```text
tests/test_paths.py
tests/test_security.py
tests/test_permissions.py
tests/test_memory_store.py
tests/test_remote_actions.py
```

## Required tests

### `tests/test_paths.py`

Test:

- safe project path resolves under project root
- `../` project rejected
- absolute project rejected
- `../` file rejected
- `.env` rejected by default
- `.env` allowed when `allow_sensitive=True`

### `tests/test_security.py`

Test:

- API key redaction
- password redaction
- token redaction
- nested dict redaction
- sensitive path detection

### `tests/test_permissions.py`

Test:

- allow passes
- deny raises
- prompt without confirm raises
- prompt with confirm passes

### `tests/test_memory_store.py`

Test:

- set/get in namespace
- list by prefix
- delete
- ttl expiry
- namespace validation

### `tests/test_remote_actions.py`

Test:

- known action builds command
- unknown action rejected
- docker logs limits lines to 200
- suspicious service names rejected or quoted safely
- remote path required for docker actions

Run:

```bash
python -m pytest -q
python -m compileall .
```

If repository has no dependency file, do not add heavy dependencies. Pytest is acceptable only for tests.

---

# Phase 16: Final verification checklist

Before finishing, Codex must verify and report:

- `python -m compileall .` passes.
- `python -m pytest -q` passes, or explain exactly why tests cannot run.
- `server.py` still imports and creates `mcp`.
- `registry.py` includes any new tool modules.
- `remote_exec` no longer runs raw shell commands by default.
- Telegram no longer sends unknown messages to Codex by default.
- Codex dangerous bypass is disabled by default.
- File path traversal is blocked.
- `.env` and SSH private keys are protected.
- Audit log is written for tool actions.
- Memory namespaces work.
- Dry-run works for write/deploy/remote/git push.
- README documents the new behavior.

---

# Expected final summary format

When done, respond with this exact structure:

```text
# devMCP Update Complete

## Files changed
- ...

## Security fixes implemented
- ...

## New features implemented
- ...

## Compatibility notes
- ...

## Tests run
- ...

## Remaining risks
- ...
```

Do not say the work is complete if tests/checks were not run. If tests could not run, state why.
