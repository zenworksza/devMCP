from __future__ import annotations

import importlib

MODULES = [
    "tools.context",
    "tools.files",
    "tools.offline_code",
    "tools.git",
    "tools.docker",
    "tools.quality",
    "tools.python_dev",
    "tools.javascript_dev",
    "tools.security",
    "tools.database",
    "tools.network",
    "tools.config",
    "tools.http_config",
    "tools.remote",
    "tools.memory",
    "tools.agents",
    "skills.workflows",
    "skills.project_health",
    "skills.scaffold",
    "skills.ops_workflows",
]


def register_all(mcp) -> None:
    for module_name in MODULES:
        module = importlib.import_module(module_name)
        module.register(mcp)
