"""
MCP Dev Server - modular entry point.

Tool implementations live in:
  - core/   shared runtime, state, command helpers
  - tools/  thin MCP wrappers around local development commands
  - skills/ multi-step workflow tools
"""

from mcp.server.fastmcp import FastMCP

from core.audit import audit_event
from core.runtime import ensure_tools
from registry import register_all


def create_server() -> FastMCP:
    mcp = FastMCP('dev-server', host='0.0.0.0', port=8000)
    register_all(mcp)
    return mcp


try:
    ensure_tools()
except Exception as exc:
    audit_event('server_start_warning', warning=f'ensure_tools failed: {exc}')
    print(f'[devMCP warning] ensure_tools failed: {exc}')

mcp = create_server()


if __name__ == '__main__':
    mcp.run(transport='streamable-http')
