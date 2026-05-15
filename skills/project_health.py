from __future__ import annotations

from core.runtime import PROJECT_ROOT, run_safe


def _section(name: str, body: str) -> str:
    return f"=== {name} ===\n{body}"


def register(mcp) -> None:
    @mcp.tool()
    def project_health_check(project: str) -> str:
        """Run a broad local project health check."""
        path = str(PROJECT_ROOT / project)
        parts = [
            _section("Git", run_safe(["git", "status", "--short"], path, "git status")),
            _section("Code Size", run_safe(["tokei", "."], path, "tokei", head_tail=True)),
            _section("Python Lint", run_safe(["ruff", "check", "."], path, "ruff", timeout=60, head_tail=True)),
            _section("Docker", run_safe(["docker", "compose", "ps"], path, "docker ps")),
        ]
        return "\n\n".join(parts)

    @mcp.tool()
    def pre_deploy_check(project: str) -> str:
        """Run pre-deploy checks: git status, compose config, lint, tests, build."""
        path = str(PROJECT_ROOT / project)
        parts = [
            _section("Git", run_safe(["git", "status", "--short"], path, "git status")),
            _section("Compose Config", run_safe(["docker", "compose", "config"], path, "compose config", timeout=60, head_tail=True)),
            _section("Lint", run_safe(["ruff", "check", "."], path, "ruff", timeout=60, head_tail=True)),
            _section("Tests", run_safe(["pytest", "--tb=short", "-q"], path, "pytest", timeout=120, head_tail=True)),
            _section("Docker Build", run_safe(["docker", "compose", "build"], path, "docker build", timeout=300, head_tail=True)),
        ]
        return "\n\n".join(parts)

    @mcp.tool()
    def docker_audit(project: str) -> str:
        """Validate compose and lint Dockerfile when tools are available."""
        path = str(PROJECT_ROOT / project)
        parts = [
            _section("Compose Config", run_safe(["docker", "compose", "config"], path, "compose config", timeout=60, head_tail=True)),
            _section("Dockerfile Lint", run_safe(["dockerfilelint", "Dockerfile"], path, "dockerfilelint", head_tail=True)),
        ]
        return "\n\n".join(parts)

    @mcp.tool()
    def security_audit(project: str) -> str:
        """Run local security checks: secrets, bandit, Dockerfile lint."""
        path = str(PROJECT_ROOT / project)
        secret_pattern = r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}"
        parts = [
            _section("Secret Scan", run_safe(["rg", "--line-number", "--hidden", "--glob", "!.git", secret_pattern, "."], path, "secret scan", head_tail=True)),
            _section("Bandit", run_safe(["bandit", "-r", "."], path, "bandit", timeout=120, head_tail=True)),
            _section("Dockerfile Lint", run_safe(["dockerfilelint", "Dockerfile"], path, "dockerfilelint", head_tail=True)),
        ]
        return "\n\n".join(parts)

    @mcp.tool()
    def offline_index_project(project: str) -> str:
        """Build local project indexes: tokei summary and ctags file."""
        path = str(PROJECT_ROOT / project)
        parts = [
            _section("Code Size", run_safe(["tokei", "."], path, "tokei", head_tail=True)),
            _section("Symbols", run_safe(["ctags", "-R", "-f", ".tags", "."], path, "ctags", timeout=120, head_tail=True)),
        ]
        return "\n\n".join(parts)

    @mcp.tool()
    def repo_map(project: str) -> str:
        """Summarize tree, language sizes, and recent git history."""
        path = str(PROJECT_ROOT / project)
        parts = [
            _section("Tree", run_safe(["find", ".", "-maxdepth", "3", "-print"], path, "tree", head_tail=True)),
            _section("Code Size", run_safe(["tokei", "."], path, "tokei", head_tail=True)),
            _section("Recent Commits", run_safe(["git", "log", "--oneline", "-10"], path, "git log")),
        ]
        return "\n\n".join(parts)
