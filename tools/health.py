from __future__ import annotations

from core.audit import AUDIT_FILE
from core.memory_store import MEMORY_DIR
from core.permissions import POLICY_FILE, load_policy
from core.runtime import CONFIG_FILE, PROJECT_ROOT, SERVER_DIR, TELEGRAM_CHAT_ID, TELEGRAM_TOKEN, TOOLS_FILE, load_json
from registry import MODULES


def register(mcp) -> None:
    @mcp.tool()
    def devmcp_health() -> str:
        policy = load_policy()
        tools = load_json(TOOLS_FILE)
        missing = sorted(name for name, info in tools.items() if info.get('status') == 'missing')
        lines = [
            f"server directory: {SERVER_DIR}",
            f"project root: {PROJECT_ROOT}",
            f"memory directory exists: {MEMORY_DIR.exists()}",
            f"audit log exists: {AUDIT_FILE.exists()}",
            f"permissions policy path: {POLICY_FILE}",
            f"permissions loaded: {bool(policy)}",
            f"config path: {CONFIG_FILE}",
            f"remote count: {len(load_json(SERVER_DIR / 'remote_servers.json'))}",
            f"known tools/modules count: {len(MODULES)}",
            f"telegram configured: {bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)}",
            f"auto-install enabled: {tools != {}}",
            f"missing common tools: {', '.join(missing) if missing else 'none'}",
        ]
        return '\n'.join(lines)
