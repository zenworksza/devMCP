# devMCP

Security warning: devMCP can read files, write files, run development commands, control Docker, and perform remote SSH operations. Do not expose it publicly. Run it only on trusted machines and networks. Dangerous operations are denied or confirmation-gated by default.

## What devMCP is

devMCP is a modular local MCP server for AI-assisted development operations. It keeps `server.py` as the FastMCP entry point and exposes tool modules under `tools/` plus higher-level workflows under `skills/`.

## Security model

- Secrets are redacted before they are returned, written to audit logs, sent to Telegram, or stored in memory.
- Dangerous operations are controlled by `permissions.json`.
- Remote shell access is allowlisted by default and raw shell is disabled unless explicitly enabled in `config.json`.
- Telegram no longer forwards unknown messages to Codex by default.

## Permission policy

`~/mcp-dev-server/permissions.json` controls `read`, `write`, `git`, `docker`, `deploy`, `remote`, `dangerous`, `network`, `database`, `agents`, `install`, and `telegram_codex_fallback`.

## Safe paths

Project paths are constrained under `~/workspaces`. Absolute paths and `..` traversal are rejected. Sensitive files such as `.env` and SSH private keys are blocked unless the call explicitly allows sensitive reads.

## Remote execution model

`remote_exec` now accepts an allowlisted `action` instead of arbitrary shell by default. Raw remote shell is disabled unless `config.json` enables it and the permission policy also allows dangerous actions.

## Telegram bot safety

- Unknown messages return a help error by default.
- `codex:` runs without dangerous bypass.
- `codex-danger:` only works if `allow_codex_dangerous_bypass` is enabled.
- `deploy`, `remote deploy`, and `git push` require `--confirm`.
- Telegram output is sent without Markdown parsing.

## Memory namespaces

Memory now lives under `~/mcp-dev-server/memory/` with one JSON file per namespace. The legacy `memory.json` store is migrated into `memory/general.json` on first use.

## Audit logs

```bash
/home/$user/mcp-dev-server/.venv/bin/python3 telegram_bot.py
```
Tool activity is appended to `~/mcp-dev-server/logs/audit.jsonl` as JSONL.

## Dry-run and confirmation usage

Use `confirm=True` and `dry_run=True` for write/deploy/remote/git operations to preview actions safely.

## Auto-install behavior

Automatic tool installation is disabled by default. Set `DEVMCP_AUTO_INSTALL=1` to allow installs, subject to permission policy.

## Agent profiles and consensus mode

Agent profiles live under `agents/`. Use `agent_profiles()` to list them, `route_profiled_task()` to run a profiled task, and `consensus_task()` to collect multiple agent responses.

## Workflows

JSON workflows live under `workflows/`. Use `workflow_list()` and `workflow_run(name, project, dry_run=True)`.

## Task queue

Task records are stored in `~/mcp-dev-server/tasks.sqlite3`. Use `task_create`, `task_list`, `task_get`, `task_complete`, and `task_fail`.
