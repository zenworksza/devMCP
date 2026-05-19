from __future__ import annotations

import json

from core.runtime import SERVER_DIR

POLICY_FILE = SERVER_DIR / "permissions.json"
DEFAULT_POLICY = {
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
    "telegram_codex_fallback": "deny",
}
VALID_POLICIES = {"allow", "prompt", "deny"}


class PermissionDenied(RuntimeError):
    pass


def load_policy() -> dict[str, str]:
    if not POLICY_FILE.exists():
        POLICY_FILE.write_text(json.dumps(DEFAULT_POLICY, indent=2), encoding="utf-8")
        return dict(DEFAULT_POLICY)

    try:
        loaded = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        loaded = {}

    policy = dict(DEFAULT_POLICY)
    for key, value in loaded.items():
        if value in VALID_POLICIES:
            policy[str(key)] = value
    if policy != loaded:
        POLICY_FILE.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    return policy


def check_permission(permission: str, *, tool: str, confirm: bool = False) -> None:
    policy = load_policy()
    state = policy.get(permission, "deny")
    if state == "allow":
        return
    if state == "deny":
        raise PermissionDenied(f"[Permission denied: {tool} requires '{permission}' permission.]")
    if confirm:
        return
    raise PermissionDenied(
        f"[Permission confirmation required: {tool} requires '{permission}'. Retry with confirm=True.]"
    )
