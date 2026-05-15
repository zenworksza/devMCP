from __future__ import annotations

from pathlib import Path

from core.runtime import (
    PROJECT_ROOT,
    apt_install,
    cmd_exists,
    npm_global,
    pip_install,
    run_safe,
)
from tools.files import cache_evict


def register(mcp) -> None:
    @mcp.tool()
    def run_tests(project: str, test_command: str = "pytest") -> str:
        """Run tests. Allowed: pytest, npm test, npm run build."""
        allowed = {
            "pytest": ["pytest", "--tb=short", "-q"],
            "npm test": ["npm", "test"],
            "npm run build": ["npm", "run", "build"],
        }
        if test_command not in allowed:
            return f"[Blocked. Allowed: {', '.join(allowed.keys())}]"
        return run_safe(allowed[test_command], str(PROJECT_ROOT / project), f"{test_command} output")

    @mcp.tool()
    def tool_status() -> str:
        """Show which dev tools are installed. Call if a tool command fails."""
        checks = {
            "rg (ripgrep)": "rg",
            "rga (ripgrep-all)": "rga",
            "fd": "fd",
            "fdfind": "fdfind",
            "bat": "bat",
            "batcat": "batcat",
            "tree": "tree",
            "tokei": "tokei",
            "ctags": "ctags",
            "delta": "delta",
            "jq": "jq",
            "yq": "yq",
            "xmllint": "xmllint",
            "shellcheck": "shellcheck",
            "shfmt": "shfmt",
            "black": "black",
            "ruff": "ruff",
            "pylint": "pylint",
            "semgrep": "semgrep",
            "bandit": "bandit",
            "pipdeptree": "pipdeptree",
            "isort": "isort",
            "autoflake": "autoflake",
            "autopep8": "autopep8",
            "mypy": "mypy",
            "vulture": "vulture",
            "radon": "radon",
            "lizard": "lizard",
            "http (httpie)": "http",
            "prettier": "prettier",
            "eslint": "eslint",
            "jscodeshift": "jscodeshift",
            "madge": "madge",
            "depcheck": "depcheck",
            "ts-prune": "ts-prune",
            "dockerfilelint": "dockerfilelint",
            "hadolint": "hadolint",
            "dive": "dive",
            "trivy": "trivy",
            "sg (ast-grep)": "sg",
            "nmap": "nmap",
            "lsof": "lsof",
            "sqlite3": "sqlite3",
            "psql": "psql",
            "redis-cli": "redis-cli",
            "csvstat": "csvstat",
            "hyperfine": "hyperfine",
            "jc": "jc",
            "watchexec": "watchexec",
        }
        return "\n".join(f"{'OK' if cmd_exists(cmd) else 'MISSING'} {label}" for label, cmd in checks.items())

    @mcp.tool()
    def tool_install(tool: str) -> str:
        """
        Install or reinstall a dev tool.
        Available: common apt/pip/npm offline development tools.
        """
        apt = {
            "ripgrep": "ripgrep",
            "fd": "fd-find",
            "bat": "bat",
            "universal-ctags": "universal-ctags",
            "ctags": "universal-ctags",
            "jq": "jq",
            "yq": "yq",
            "xmllint": "libxml2-utils",
            "shellcheck": "shellcheck",
            "shfmt": "shfmt",
            "lsof": "lsof",
            "sqlite3": "sqlite3",
            "nmap": "nmap",
            "tree": "tree",
            "postgresql-client": "postgresql-client",
            "psql": "postgresql-client",
            "redis-cli": "redis-tools",
            "redis-tools": "redis-tools",
            "hyperfine": "hyperfine",
            "tokei": "tokei",
            "git-delta": "git-delta",
            "delta": "git-delta",
            "ripgrep-all": "ripgrep-all",
            "rga": "ripgrep-all",
            "jc": "jc",
            "watchexec": "watchexec",
        }
        pip = {
            "black": "black",
            "ruff": "ruff",
            "pylint": "pylint",
            "semgrep": "semgrep",
            "httpie": "httpie",
            "bandit": "bandit",
            "pipdeptree": "pipdeptree",
            "isort": "isort",
            "autoflake": "autoflake",
            "autopep8": "autopep8",
            "mypy": "mypy",
            "vulture": "vulture",
            "radon": "radon",
            "lizard": "lizard",
            "csvkit": "csvkit",
        }
        npm = {
            "prettier": "prettier",
            "eslint": "eslint",
            "jscodeshift": "jscodeshift",
            "madge": "madge",
            "depcheck": "depcheck",
            "dockerfilelint": "dockerfilelint",
            "ts-prune": "ts-prune",
        }
        target = tool.lower().strip()
        if target in apt:
            return apt_install(apt[target])
        if target in pip:
            return pip_install(pip[target])
        if target in npm:
            return npm_global(npm[target])
        if target == "ast-grep":
            if cmd_exists("cargo"):
                return run_safe(["cargo", "install", "ast-grep", "--quiet"], label="cargo", timeout=300)
            return npm_global("@ast-grep/cli")
        return f"[Unknown tool: {tool}]"

    @mcp.tool()
    def lint(project: str, file_path: str, linter: str = "auto") -> str:
        """
        Lint a file. linter=auto detects by extension (.py -> ruff, .js/.ts -> eslint).
        """
        full_path = str(PROJECT_ROOT / project / file_path)
        ext = Path(file_path).suffix.lower()
        if linter == "auto":
            linter = "ruff" if ext == ".py" else "eslint" if ext in (".js", ".ts", ".jsx", ".tsx") else "ruff"
        cmds = {
            "ruff": ["ruff", "check", full_path],
            "pylint": ["pylint", "--output-format=text", full_path],
            "eslint": ["eslint", "--format=compact", full_path],
            "semgrep": ["semgrep", "--config=auto", "--quiet", full_path],
        }
        if linter not in cmds:
            return f"[Unknown linter: {linter}]"
        return run_safe(cmds[linter], label=f"{linter} output", timeout=60)

    @mcp.tool()
    def lint_project(project: str, linter: str = "auto") -> str:
        """Lint entire project. auto runs ruff on Python and eslint on JS/TS."""
        path = str(PROJECT_ROOT / project)
        results = []
        if linter in ("auto", "ruff") and cmd_exists("ruff"):
            results.append(f"=== ruff ===\n{run_safe(['ruff', 'check', '.'], path, 'ruff', timeout=60)}")
        if linter in ("auto", "eslint") and cmd_exists("eslint"):
            results.append(
                "=== eslint ===\n"
                + run_safe(["eslint", "--format=compact", "--ext", ".js,.ts,.jsx,.tsx", "."], path, "eslint", timeout=60)
            )
        return "\n".join(results) or "[No linters ran - check tool_status()]"

    @mcp.tool()
    def format_file(project: str, file_path: str, formatter: str = "auto") -> str:
        """
        Format a file in place. auto detects by extension (.py -> black, others -> prettier).
        """
        full_path = str(PROJECT_ROOT / project / file_path)
        ext = Path(file_path).suffix.lower()
        if formatter == "auto":
            formatter = "black" if ext == ".py" else "prettier"
        cmds = {
            "black": ["black", "--quiet", full_path],
            "prettier": ["prettier", "--write", full_path],
        }
        if formatter not in cmds:
            return f"[Unknown formatter: {formatter}]"
        result = run_safe(cmds[formatter], label=f"{formatter} output")
        cache_evict(project, file_path)
        return result + f"\n[Cache invalidated: {file_path}]"

    @mcp.tool()
    def analyse_code(project: str, file_path: str) -> str:
        """
        Full static analysis: lint + semgrep security scan.
        """
        results = ["=== Lint ===", lint(project, file_path)]
        if cmd_exists("semgrep"):
            full_path = str(PROJECT_ROOT / project / file_path)
            results += [
                "=== Security (semgrep) ===",
                run_safe(["semgrep", "--config=auto", "--quiet", full_path], label="semgrep", timeout=120),
            ]
        return "\n".join(results)

    @mcp.tool()
    def ast_search(project: str, pattern: str, language: str = "python") -> str:
        """
        Structural code search using ast-grep (sg).
        """
        if not cmd_exists("sg"):
            return "[ast-grep not installed. Run tool_install('ast-grep')]"
        return run_safe(
            ["sg", "run", "--pattern", pattern, "--lang", language, "."],
            str(PROJECT_ROOT / project),
            "ast-grep",
            timeout=60,
        )
