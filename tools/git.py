from __future__ import annotations

import re

from core.runtime import PROJECT_ROOT, run_safe, telegram_send


def register(mcp) -> None:
    @mcp.tool()
    def list_projects() -> str:
        """List available project folders in ~/workspaces."""
        if not PROJECT_ROOT.exists():
            return f"[workspaces not found at {PROJECT_ROOT}]"
        return "\n".join(p.name for p in sorted(PROJECT_ROOT.iterdir()) if p.is_dir())

    @mcp.tool()
    def git_status(project: str) -> str:
        """Show git status (short format)."""
        return run_safe(["git", "status", "--short"], str(PROJECT_ROOT / project), "git status")

    @mcp.tool()
    def git_diff(project: str, path_filter: str = "") -> str:
        """Show git diff. Use path_filter to limit to one file."""
        cmd = ["git", "diff"] + (["--", path_filter] if path_filter else [])
        return run_safe(cmd, str(PROJECT_ROOT / project), "git diff", head_tail=True)

    @mcp.tool()
    def git_log(project: str, n: int = 10) -> str:
        """Show last N commits (max 50), one line each."""
        return run_safe(["git", "log", "--oneline", f"-{min(n, 50)}"], str(PROJECT_ROOT / project), "git log")

    @mcp.tool()
    def git_pull(project: str) -> str:
        """Pull latest changes from remote."""
        return run_safe(["git", "pull"], str(PROJECT_ROOT / project), "git pull")

    @mcp.tool()
    def git_clone(repo_url: str, project_name: str) -> str:
        """Clone a repo into ~/workspaces/<project_name>."""
        return run_safe(["git", "clone", repo_url, project_name], str(PROJECT_ROOT), "git clone", timeout=120)

    @mcp.tool()
    def git_push_staging(project: str, commit_message: str, pr_description: str = "") -> str:
        """
        Commit all changes, push to staging branch, notify via Telegram with PR link.
        ONLY call this after code is confirmed working via deploy_local() + http_request().
        """
        path = str(PROJECT_ROOT / project)
        run_safe(["git", "add", "-A"], path)
        commit_out = run_safe(["git", "commit", "-m", commit_message], path)
        if "nothing to commit" in commit_out:
            return "[Nothing to commit - working tree clean]"
        run_safe(["git", "checkout", "-B", "staging"], path)
        push_out = run_safe(["git", "push", "origin", "staging", "--force-with-lease"], path, timeout=60)
        remote_url = run_safe(["git", "remote", "get-url", "origin"], path).strip()
        pr_link = ""
        if "github.com" in remote_url:
            clean = re.sub(r"git@github\.com:", "https://github.com/", remote_url).rstrip(".git")
            pr_link = f"{clean}/compare/staging?expand=1"
        msg = [f"*{project}* - staging updated", f"{commit_message}"]
        if pr_description:
            msg.append(f"_{pr_description}_")
        if pr_link:
            msg.append(f"[Open PR]({pr_link})")
        msg.append("Please review and merge to main.")
        telegram_send("\n".join(msg))
        return f"{commit_out}\n{push_out}\nTelegram notification sent."
