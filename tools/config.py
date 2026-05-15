from __future__ import annotations

import json

from core.runtime import PROJECT_ROOT, cmd_exists, run_safe


def register(mcp) -> None:
    @mcp.tool()
    def env_check(project: str, env_file: str = ".env", required: str = "") -> str:
        """Verify required environment variables are present in an env file."""
        path = PROJECT_ROOT / project / env_file
        if not path.exists():
            return f"[Env file not found: {env_file}]"
        values = {}
        for line in path.read_text(errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
        required_keys = [item.strip() for item in required.split(",") if item.strip()]
        if not required_keys:
            return f"{env_file}: {len(values)} variable(s) found. Provide required='A,B,C' to validate specific keys."
        missing = [key for key in required_keys if not values.get(key)]
        if missing:
            return "[Missing env vars]\n" + "\n".join(missing)
        return f"[OK] All required env vars present: {', '.join(required_keys)}"

    @mcp.tool()
    def compose_validate(project: str) -> str:
        """Validate docker-compose.yml syntax with docker compose config."""
        return run_safe(["docker", "compose", "config"], str(PROJECT_ROOT / project), "compose config", timeout=60, head_tail=True)

    @mcp.tool()
    def yaml_query(project: str, file_path: str, query: str = ".") -> str:
        """Run yq against a YAML file."""
        if not cmd_exists("yq"):
            return "[yq not installed]"
        return run_safe(["yq", query, file_path], str(PROJECT_ROOT / project), "yq output", head_tail=True)

    @mcp.tool()
    def xml_validate(project: str, file_path: str) -> str:
        """Validate XML with xmllint."""
        if not cmd_exists("xmllint"):
            return "[xmllint not installed]"
        return run_safe(["xmllint", "--noout", file_path], str(PROJECT_ROOT / project), "xmllint output")

    @mcp.tool()
    def shell_lint(project: str, file_path: str) -> str:
        """Lint a shell script with shellcheck."""
        if not cmd_exists("shellcheck"):
            return "[shellcheck not installed]"
        return run_safe(["shellcheck", file_path], str(PROJECT_ROOT / project), "shellcheck output", head_tail=True)

    @mcp.tool()
    def shell_format(project: str, file_path: str, write: bool = False) -> str:
        """Format a shell script with shfmt."""
        if not cmd_exists("shfmt"):
            return "[shfmt not installed]"
        cmd = ["shfmt", "-w" if write else "-d", file_path]
        return run_safe(cmd, str(PROJECT_ROOT / project), "shfmt output", head_tail=True)

    @mcp.tool()
    def json_validate(project: str, file_path: str) -> str:
        """Validate JSON using Python's JSON parser."""
        path = PROJECT_ROOT / project / file_path
        try:
            json.loads(path.read_text())
            return f"[OK] Valid JSON: {file_path}"
        except Exception as exc:
            return f"[Invalid JSON: {file_path}]\n{exc}"
