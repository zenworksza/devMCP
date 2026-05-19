from __future__ import annotations

import re
from pathlib import Path

from core.runtime import PROJECT_ROOT
from core.security import is_sensitive_path


class UnsafePathError(ValueError):
    pass


def _reject_path_parts(raw: str, *, field: str) -> Path:
    if not raw or not str(raw).strip():
        raise UnsafePathError(f"{field} is required")
    path = Path(str(raw).strip())
    if path.is_absolute():
        raise UnsafePathError(f"{field} must not be absolute")
    if any(part == '..' for part in path.parts):
        raise UnsafePathError(f"{field} must not contain '..'")
    if any(part == '~' for part in path.parts):
        raise UnsafePathError(f"{field} must not contain '~'")
    return path


def _ensure_within(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise UnsafePathError(f"path escapes allowed root: {resolved_candidate}") from exc
    return resolved_candidate


def safe_project_path(project: str) -> Path:
    rel = _reject_path_parts(project, field='project')
    return _ensure_within(PROJECT_ROOT, PROJECT_ROOT / rel)


def safe_project_file(
    project: str,
    file_path: str,
    *,
    must_exist: bool = False,
    allow_sensitive: bool = False,
) -> Path:
    root = safe_project_path(project)
    rel = _reject_path_parts(file_path, field='file_path')
    candidate = _ensure_within(root, root / rel)
    if is_sensitive_path(str(rel)) and not allow_sensitive:
        raise UnsafePathError(f"sensitive file blocked: {file_path}")
    if must_exist and not candidate.exists():
        raise UnsafePathError(f"file not found: {file_path}")
    return candidate


def safe_project_cwd(project: str) -> str:
    return str(safe_project_path(project))


def safe_new_project_name(project_name: str) -> str:
    name = str(project_name).strip()
    _reject_path_parts(name, field='project_name')
    if '/' in name or '\\' in name:
        raise UnsafePathError('project_name must be a single directory name')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', name):
        raise UnsafePathError('project_name contains unsupported characters')
    return name
