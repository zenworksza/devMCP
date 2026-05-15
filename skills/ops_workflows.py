from __future__ import annotations

import json
import time
from pathlib import Path

from core.runtime import PROJECT_ROOT, run_safe


def _section(name: str, body: str) -> str:
    return f"=== {name} ===\n{body}"


def _package_json_scripts(project: str) -> dict:
    path = PROJECT_ROOT / project / "package.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()).get("scripts", {})
    except Exception:
        return {}


def register(mcp) -> None:
    @mcp.tool()
    def ci_debug_workflow(project: str) -> str:
        """Collect likely CI failure context: status, lint, tests, build scripts."""
        path = str(PROJECT_ROOT / project)
        scripts = _package_json_scripts(project)
        parts = [_section("Git", run_safe(["git", "status", "--short"], path, "git status"))]
        if "lint" in scripts:
            parts.append(_section("npm lint", run_safe(["npm", "run", "lint"], path, "npm lint", timeout=120, head_tail=True)))
        parts.append(_section("pytest", run_safe(["pytest", "--tb=short", "-q"], path, "pytest", timeout=120, head_tail=True)))
        if "build" in scripts:
            parts.append(_section("npm build", run_safe(["npm", "run", "build"], path, "npm build", timeout=180, head_tail=True)))
        return "\n\n".join(parts)

    @mcp.tool()
    def pr_review_workflow(project: str, base: str = "origin/main") -> str:
        """Review local changes against a base branch with diff, tests, and risk scans."""
        path = str(PROJECT_ROOT / project)
        parts = [
            _section("Changed Files", run_safe(["git", "diff", "--name-status", base], path, "changed files")),
            _section("Diff Summary", run_safe(["git", "diff", "--stat", base], path, "diff stat")),
            _section("Lint", run_safe(["ruff", "check", "."], path, "ruff", timeout=60, head_tail=True)),
            _section("Tests", run_safe(["pytest", "--tb=short", "-q"], path, "pytest", timeout=120, head_tail=True)),
        ]
        return "\n\n".join(parts)

    @mcp.tool()
    def dependency_upgrade_workflow(project: str) -> str:
        """Inspect Python and npm dependency state without changing files."""
        path = str(PROJECT_ROOT / project)
        parts = [
            _section("Python Dependency Tree", run_safe(["pipdeptree"], path, "pipdeptree", head_tail=True)),
            _section("npm outdated", run_safe(["npm", "outdated"], path, "npm outdated", timeout=120, head_tail=True)),
            _section("depcheck", run_safe(["depcheck"], path, "depcheck", timeout=120, head_tail=True)),
        ]
        return "\n\n".join(parts)

    @mcp.tool()
    def docker_optimize_workflow(project: str, image: str = "") -> str:
        """Inspect Docker build/config and optionally image layers."""
        path = str(PROJECT_ROOT / project)
        parts = [
            _section("Compose Config", run_safe(["docker", "compose", "config"], path, "compose config", timeout=60, head_tail=True)),
            _section("Dockerfile Lint", run_safe(["dockerfilelint", "Dockerfile"], path, "dockerfilelint", head_tail=True)),
        ]
        if image:
            parts.append(_section("Dive", run_safe(["dive", image, "--ci"], path, "dive", timeout=300, head_tail=True)))
        return "\n\n".join(parts)

    @mcp.tool()
    def incident_debug_workflow(project: str, service: str = "", url: str = "") -> str:
        """Collect local runtime status, logs, stats, and optional HTTP health response."""
        path = str(PROJECT_ROOT / project)
        parts = [
            _section("Compose PS", run_safe(["docker", "compose", "ps"], path, "docker ps")),
            _section("Docker Stats", run_safe(["docker", "stats", "--no-stream"], path, "docker stats", timeout=30, head_tail=True)),
        ]
        if service:
            parts.append(_section("Service Logs", run_safe(["docker", "compose", "logs", "--tail", "120", service], path, "logs", head_tail=True)))
        if url:
            parts.append(_section("HTTP", run_safe(["curl", "-i", "--max-time", "10", url], path, "curl", timeout=15, head_tail=True)))
        return "\n\n".join(parts)

    @mcp.tool()
    def log_triage_workflow(project: str, service: str, pattern: str = "error|exception|traceback|failed") -> str:
        """Search recent Docker logs for likely failure lines."""
        path = str(PROJECT_ROOT / project)
        logs = run_safe(["docker", "compose", "logs", "--tail", "500", service], path, "logs", head_tail=True)
        matches = run_safe(["docker", "compose", "logs", "--tail", "500", service], path, "logs raw", head_tail=True)
        rg = run_safe(["rg", "-i", pattern], path, "log pattern", head_tail=True)
        return "\n\n".join([_section("Recent Logs", logs), _section("Pattern", pattern), _section("Project Pattern Search", rg), _section("Raw Log Snapshot", matches)])

    @mcp.tool()
    def api_contract_check(project: str, openapi_file: str = "openapi.json") -> str:
        """Validate and summarize an OpenAPI JSON document."""
        path = PROJECT_ROOT / project / openapi_file
        if not path.exists():
            return f"[OpenAPI file not found: {openapi_file}]"
        try:
            doc = json.loads(path.read_text())
        except Exception as exc:
            return f"[Invalid OpenAPI JSON]\n{exc}"
        paths = doc.get("paths", {})
        methods = sum(len(v) for v in paths.values() if isinstance(v, dict))
        return f"[OK] {openapi_file}\nTitle: {doc.get('info', {}).get('title', '')}\nPaths: {len(paths)}\nOperations: {methods}"

    @mcp.tool()
    def openapi_validate(project: str, openapi_file: str = "openapi.json") -> str:
        """Validate OpenAPI JSON with swagger-cli if installed, otherwise JSON parse."""
        path = str(PROJECT_ROOT / project)
        if Path(path, openapi_file).suffix == ".json":
            parse = api_contract_check(project, openapi_file)
        else:
            parse = run_safe(["yq", ".", openapi_file], path, "yq", head_tail=True)
        swagger = run_safe(["swagger-cli", "validate", openapi_file], path, "swagger-cli", timeout=60, head_tail=True)
        return _section("Parse", parse) + "\n\n" + _section("swagger-cli", swagger)

    @mcp.tool()
    def openapi_generate_client(project: str, openapi_file: str = "openapi.json", output_dir: str = "generated-client") -> str:
        """Generate a client with openapi-generator-cli if installed."""
        path = str(PROJECT_ROOT / project)
        return run_safe(
            ["openapi-generator-cli", "generate", "-i", openapi_file, "-g", "typescript-fetch", "-o", output_dir],
            path,
            "openapi-generator",
            timeout=300,
            head_tail=True,
        )

    @mcp.tool()
    def postgres_migration_review(project: str) -> str:
        """Review Alembic migration heads/history/current state."""
        path = str(PROJECT_ROOT / project)
        return "\n\n".join(
            [
                _section("Alembic Current", run_safe(["alembic", "current"], path, "alembic current")),
                _section("Alembic Heads", run_safe(["alembic", "heads"], path, "alembic heads")),
                _section("Recent Versions", run_safe(["find", "alembic/versions", "-maxdepth", "1", "-type", "f"], path, "versions", head_tail=True)),
            ]
        )

    @mcp.tool()
    def backup_rotation_workflow(project: str, backup_dir: str = "backups", keep: int = 10) -> str:
        """List backups and identify files beyond the keep count without deleting them."""
        path = PROJECT_ROOT / project / backup_dir
        if not path.exists():
            return f"[Backup directory not found: {backup_dir}]"
        files = sorted([p for p in path.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
        kept = files[:keep]
        stale = files[keep:]
        return "\n".join(
            ["Kept:"] + [str(p) for p in kept] + ["", "Stale candidates:"] + [str(p) for p in stale]
        )

    @mcp.tool()
    def secret_rotation_workflow(project: str) -> str:
        """Find likely secrets and list rotation checklist steps."""
        path = str(PROJECT_ROOT / project)
        pattern = r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}"
        findings = run_safe(["rg", "--line-number", "--hidden", "--glob", "!.git", pattern, "."], path, "secret scan", head_tail=True)
        checklist = "\n".join(
            [
                "1. Revoke exposed secret in provider console.",
                "2. Generate replacement secret.",
                "3. Store replacement in deployment secret manager or .env outside git.",
                "4. Redeploy affected services.",
                "5. Verify old secret no longer works.",
            ]
        )
        return _section("Findings", findings) + "\n\n" + _section("Rotation Checklist", checklist)

    @mcp.tool()
    def local_model_tooling_check() -> str:
        """Check local AI/model tooling availability."""
        checks = ["ollama", "llama-server", "llama-cli", "python", "python3", "nvidia-smi"]
        return "\n".join(f"{cmd}: {run_safe(['which', cmd], label=cmd).strip() or 'missing'}" for cmd in checks)

    @mcp.tool()
    def offline_docs_index(project: str, docs_dir: str = "docs") -> str:
        """Create a simple local docs file list and searchable text snapshot."""
        path = str(PROJECT_ROOT / project)
        docs_path = PROJECT_ROOT / project / docs_dir
        if not docs_path.exists():
            return f"[Docs directory not found: {docs_dir}]"
        index_dir = PROJECT_ROOT / project / ".mcp-index"
        index_dir.mkdir(exist_ok=True)
        out = index_dir / f"docs-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        listing = run_safe(["find", docs_dir, "-type", "f"], path, "docs list", head_tail=True)
        out.write_text(listing)
        return f"[Docs index written: {out}]\n{listing}"

    @mcp.tool()
    def release_notes_generate(project: str, since: str = "origin/main") -> str:
        """Generate release note raw material from git log."""
        path = str(PROJECT_ROOT / project)
        return run_safe(["git", "log", "--oneline", f"{since}..HEAD"], path, "release notes", head_tail=True)

    @mcp.tool()
    def changelog_generate(project: str, since: str = "origin/main") -> str:
        """Generate a changelog-style summary from commits and changed files."""
        path = str(PROJECT_ROOT / project)
        commits = run_safe(["git", "log", "--oneline", f"{since}..HEAD"], path, "commits", head_tail=True)
        files = run_safe(["git", "diff", "--name-status", since], path, "files", head_tail=True)
        return _section("Commits", commits) + "\n\n" + _section("Files", files)

    @mcp.tool()
    def license_audit(project: str) -> str:
        """Collect dependency license information where local tooling supports it."""
        path = str(PROJECT_ROOT / project)
        return "\n\n".join(
            [
                _section("pip licenses", run_safe(["pip-licenses"], path, "pip-licenses", head_tail=True)),
                _section("npm licenses", run_safe(["npx", "--yes", "license-checker", "--summary"], path, "license-checker", timeout=120, head_tail=True)),
            ]
        )
