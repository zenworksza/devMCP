from __future__ import annotations

from core.runtime import PROJECT_ROOT, cmd_exists, run_safe

SECRET_PATTERNS = (
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}",
    r"AKIA[0-9A-Z]{16}",
    r"ghp_[A-Za-z0-9_]{30,}",
    r"-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----",
)


def register(mcp) -> None:
    @mcp.tool()
    def secret_scan(project: str, path_filter: str = ".") -> str:
        """Scan source files for common hardcoded secret patterns using ripgrep."""
        if not cmd_exists("rg"):
            return "[rg not installed]"
        results = []
        for pattern in SECRET_PATTERNS:
            out = run_safe(
                ["rg", "--line-number", "--hidden", "--glob", "!.git", pattern, path_filter],
                str(PROJECT_ROOT / project),
                f"secret pattern {pattern}",
                head_tail=True,
            )
            if out.strip():
                results.append(f"=== Pattern ===\n{pattern}\n{out}")
        return "\n\n".join(results) if results else "[No obvious secrets found]"

    @mcp.tool()
    def bandit_scan(project: str, path_filter: str = ".") -> str:
        """Run offline Python security scanning with bandit."""
        if not cmd_exists("bandit"):
            return "[bandit not installed]"
        return run_safe(["bandit", "-r", path_filter], str(PROJECT_ROOT / project), "bandit output", timeout=120, head_tail=True)

    @mcp.tool()
    def dockerfile_lint(project: str, dockerfile: str = "Dockerfile") -> str:
        """Lint a Dockerfile with hadolint or dockerfilelint."""
        path = str(PROJECT_ROOT / project)
        if cmd_exists("hadolint"):
            return run_safe(["hadolint", dockerfile], path, "hadolint output", head_tail=True)
        if cmd_exists("dockerfilelint"):
            return run_safe(["dockerfilelint", dockerfile], path, "dockerfilelint output", head_tail=True)
        return "[No Dockerfile linter installed. Install hadolint or dockerfilelint.]"

    @mcp.tool()
    def trivy_fs_scan(project: str, path_filter: str = ".") -> str:
        """Run Trivy filesystem scan. Requires a local/cached vulnerability DB for offline use."""
        if not cmd_exists("trivy"):
            return "[trivy not installed]"
        return run_safe(["trivy", "fs", "--skip-db-update", path_filter], str(PROJECT_ROOT / project), "trivy fs", timeout=300, head_tail=True)

    @mcp.tool()
    def trivy_image_scan(image: str) -> str:
        """Run Trivy image scan. Requires a local/cached vulnerability DB for offline use."""
        if not cmd_exists("trivy"):
            return "[trivy not installed]"
        return run_safe(["trivy", "image", "--skip-db-update", image], label="trivy image", timeout=300, head_tail=True)

    @mcp.tool()
    def docker_image_layers(image: str) -> str:
        """Inspect Docker image layers with dive."""
        if not cmd_exists("dive"):
            return "[dive not installed]"
        return run_safe(["dive", image, "--ci"], label="dive output", timeout=300, head_tail=True)
