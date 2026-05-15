from __future__ import annotations

import re

from core.runtime import PROJECT_ROOT, run_safe, telegram_send


def register(mcp) -> None:
    @mcp.tool()
    def docker_compose_ps(project: str) -> str:
        """Show docker compose service status."""
        return run_safe(["docker", "compose", "ps"], str(PROJECT_ROOT / project), "docker ps")

    @mcp.tool()
    def docker_compose_logs(project: str, service: str, lines: int = 50) -> str:
        """Show docker compose logs for one service (max 200 lines)."""
        return run_safe(
            ["docker", "compose", "logs", "--tail", str(min(lines, 200)), service],
            str(PROJECT_ROOT / project),
            f"{service} logs",
            head_tail=True,
        )

    @mcp.tool()
    def docker_compose_build(project: str, service: str = "") -> str:
        """Build docker compose services. Optionally scope to one service."""
        cmd = ["docker", "compose", "build"] + ([service] if service else [])
        return run_safe(cmd, str(PROJECT_ROOT / project), "docker build", timeout=300)

    @mcp.tool()
    def docker_compose_restart(project: str, service: str = "") -> str:
        """Restart docker compose services. Optionally scope to one service."""
        cmd = ["docker", "compose", "restart"] + ([service] if service else [])
        return run_safe(cmd, str(PROJECT_ROOT / project), "docker restart")

    @mcp.tool()
    def deploy_local(project: str, service: str = "", run_tests_first: bool = False) -> str:
        """
        Full local deploy cycle: [tests ->] build -> up -d -> ps.
        Sends Telegram notification on completion or test failure.
        """
        path = str(PROJECT_ROOT / project)
        results = []

        if run_tests_first:
            test_out = run_safe(["pytest", "--tb=short", "-q"], path, "pytest")
            results.append(f"=== Tests ===\n{test_out}")
            if "failed" in test_out or "error" in test_out.lower():
                telegram_send(f"*{project}* - deploy aborted, tests failed.\n```\n{test_out[:400]}\n```")
                return "\n".join(results) + "\n[Deploy aborted - fix failing tests first]"

        build_cmd = ["docker", "compose", "build"] + ([service] if service else [])
        results.append(f"=== Build ===\n{run_safe(build_cmd, path, 'build', timeout=300)}")

        up_cmd = ["docker", "compose", "up", "-d"] + (["--no-deps", service] if service else [])
        results.append(f"=== Up ===\n{run_safe(up_cmd, path, 'up', timeout=120)}")

        ps_out = run_safe(["docker", "compose", "ps"], path)
        results.append(f"=== Status ===\n{ps_out}")

        telegram_send(f"*{project}* - local deploy complete.\n```\n{ps_out[:300]}\n```")
        return "\n".join(results)

    @mcp.tool()
    def audit_named_volumes(project: str) -> str:
        """
        Inspect docker-compose.yml for bind mounts that should be named volumes.
        """
        compose_path = PROJECT_ROOT / project / "docker-compose.yml"
        if not compose_path.exists():
            return f"[docker-compose.yml not found in {project}]"
        content = compose_path.read_text()
        matches = re.findall(r'^\s+- (\.\.?/[^:"\s]+:[^"\s]+)', content, re.MULTILINE)
        if not matches:
            return "[No bind mounts found]"
        lines = [f"Found {len(matches)} bind mount(s) to review:"]
        for match in matches:
            lines.append(f"  {match}")
        lines += ["", "Convert code dirs to named volumes + Dockerfile COPY.", "Keep config file mounts as bind mounts."]
        return "\n".join(lines)
