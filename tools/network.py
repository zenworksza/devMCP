from __future__ import annotations

from core.runtime import cmd_exists, run_safe


def register(mcp) -> None:
    @mcp.tool()
    def port_check(port: int, host: str = "127.0.0.1") -> str:
        """Check whether a TCP port is listening locally."""
        return run_safe(["ss", "-ltnp", f"sport = :{port}"], label=f"port {host}:{port}")

    @mcp.tool()
    def process_on_port(port: int) -> str:
        """Show the process listening on a port using lsof or ss."""
        if cmd_exists("lsof"):
            return run_safe(["lsof", "-i", f":{port}", "-P", "-n"], label="lsof output")
        return run_safe(["ss", "-ltnp", f"sport = :{port}"], label="ss output")

    @mcp.tool()
    def local_port_scan(target: str = "127.0.0.1", ports: str = "1-1024") -> str:
        """Run a local nmap port scan."""
        if not cmd_exists("nmap"):
            return "[nmap not installed]"
        return run_safe(["nmap", "-p", ports, target], label="nmap output", timeout=120, head_tail=True)

    @mcp.tool()
    def service_health_check(url: str) -> str:
        """Check an HTTP service with curl."""
        if not cmd_exists("curl"):
            return "[curl not installed]"
        return run_safe(["curl", "-i", "--max-time", "10", url], label="curl output", timeout=15, head_tail=True)

    @mcp.tool()
    def docker_stats_snapshot() -> str:
        """Capture a one-shot docker stats snapshot."""
        return run_safe(["docker", "stats", "--no-stream"], label="docker stats", timeout=30, head_tail=True)
