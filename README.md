# devMCP

Modular MCP development server for local/offline coding agents.

## Layout

- `server.py` - FastMCP entry point
- `registry.py` - module registration list
- `core/` - shared runtime, command helpers, state helpers
- `tools/` - thin MCP wrappers around local development tools
- `skills/` - higher-level multi-step workflows

## Run

```bash
/home/mdb/mcp-dev-server/.venv/bin/python3 server.py
```

The server listens on `0.0.0.0:8000` using FastMCP streamable HTTP.
