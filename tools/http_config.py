from __future__ import annotations

from core.runtime import PROJECT_ROOT, cmd_exists, run_safe


def register(mcp) -> None:
    @mcp.tool()
    def http_request(method: str, url: str, headers: str = "", body: str = "") -> str:
        """
        Make an HTTP request using httpie to test API endpoints.
        headers: space-separated "Key:Value" pairs
        body: JSON string for POST/PUT/PATCH
        """
        if not cmd_exists("http"):
            return "[httpie not installed. Run tool_install('httpie')]"
        cmd = ["http", "--ignore-stdin", "--timeout=10", method.upper(), url]
        if headers:
            cmd += headers.split()
        if body:
            cmd += ["--raw", body]
        return run_safe(cmd, label="http response", timeout=15)

    @mcp.tool()
    def jq_query(project: str, file_path: str, query: str) -> str:
        """Run a jq query against a JSON file."""
        if not cmd_exists("jq"):
            return "[jq not installed. Run tool_install('jq')]"
        return run_safe(["jq", query, str(PROJECT_ROOT / project / file_path)], label="jq output")
