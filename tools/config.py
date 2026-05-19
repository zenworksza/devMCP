from __future__ import annotations

import json

from core.paths import UnsafePathError, safe_project_file


def register(mcp) -> None:
    @mcp.tool()
    def env_check(project: str, env_file: str = '.env', required: str = '') -> str:
        try:
            path = safe_project_file(project, env_file, must_exist=True, allow_sensitive=True)
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"
        values = {}
        for line in path.read_text(errors='replace').splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                continue
            key, value = stripped.split('=', 1)
            values[key.strip()] = value.strip()
        required_keys = [item.strip() for item in required.split(',') if item.strip()]
        if not required_keys:
            return f"{env_file}: {len(values)} variable(s) found. Provide required='A,B,C' to validate specific keys."
        missing = [key for key in required_keys if not values.get(key)]
        if missing:
            return '[Missing env vars]\n' + '\n'.join(missing)
        return f"[OK] All required env vars present: {', '.join(required_keys)}"

    @mcp.tool()
    def json_validate(project: str, file_path: str) -> str:
        try:
            path = safe_project_file(project, file_path, must_exist=True, allow_sensitive=True)
            json.loads(path.read_text())
            return f"[OK] Valid JSON: {file_path}"
        except UnsafePathError as exc:
            return f"[Unsafe path: {exc}]"
        except Exception as exc:
            return f"[Invalid JSON: {file_path}]\n{exc}"
