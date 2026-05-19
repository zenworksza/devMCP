from __future__ import annotations

import json

from core.audit import audit_event
from core.paths import safe_project_cwd
from core.runtime import SERVER_DIR, run_safe

WORKFLOW_DIR = SERVER_DIR / 'workflows'


def _tool_map():
    return {
        'git_status': lambda project, args: run_safe(['git', 'status', '--short'], safe_project_cwd(project), 'git status'),
        'docker_compose_ps': lambda project, args: run_safe(['docker', 'compose', 'ps'], safe_project_cwd(project), 'docker ps'),
        'run_tests': lambda project, args: run_safe(
            ['pytest', '--tb=short', '-q'] if args.get('test_command', 'pytest') == 'pytest' else [args.get('test_command', 'pytest')],
            safe_project_cwd(project),
            'run tests',
            timeout=180,
        ),
    }


def list_workflows() -> list[str]:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(path.stem for path in WORKFLOW_DIR.glob('*.json'))


def load_workflow(name: str) -> dict:
    path = WORKFLOW_DIR / f'{name}.json'
    return json.loads(path.read_text(encoding='utf-8'))


def run_workflow(name: str, project: str, dry_run: bool = True, confirm: bool = False) -> str:
    workflow = load_workflow(name)
    allowed = _tool_map()
    report = [f"# Workflow: {workflow.get('name', name)}", '', workflow.get('description', '')]
    audit_event('workflow_start', workflow=name, project=project, dry_run=dry_run, confirm=confirm)
    for index, step in enumerate(workflow.get('steps', []), start=1):
        tool = step.get('tool', '')
        args = step.get('args', {})
        if tool not in allowed:
            body = f"[Skipped unknown workflow tool: {tool}]"
            report += [f"## Step {index}: {tool}", body, '']
            audit_event('workflow_step', workflow=name, step=index, tool=tool, status='skipped')
            continue
        if dry_run:
            body = f"[Dry run] would execute `{tool}` with args {json.dumps(args, sort_keys=True)}"
            audit_event('workflow_step', workflow=name, step=index, tool=tool, status='planned')
        else:
            body = allowed[tool](project, args)
            audit_event('workflow_step', workflow=name, step=index, tool=tool, status='ran')
        report += [f"## Step {index}: {tool}", body, '']
    audit_event('workflow_end', workflow=name, project=project, dry_run=dry_run)
    return '\n'.join(report).strip()
