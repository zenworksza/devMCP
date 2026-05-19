from __future__ import annotations

import json
import re
import time
from pathlib import Path

from core.runtime import MEMORY_FILE, SERVER_DIR
from core.security import redact_text

MEMORY_DIR = SERVER_DIR / 'memory'
MIGRATION_MARKER = MEMORY_DIR / '.migration_done'
_NS_RE = re.compile(r'^[a-z0-9_-]+$')


def normalize_namespace(namespace: str) -> str:
    value = str(namespace or 'general').strip().lower()
    if not _NS_RE.fullmatch(value):
        raise ValueError('namespace must contain only lowercase letters, numbers, underscore, and dash')
    return value


def _namespace_file(namespace: str) -> Path:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    return MEMORY_DIR / f"{normalize_namespace(namespace)}.json"


def _namespace_path(namespace: str) -> Path:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_memory()
    return _namespace_file(namespace)


def _now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def _expired(entry: dict) -> bool:
    expires = entry.get('expires')
    return bool(expires and expires <= _now())


def _load_namespace(namespace: str) -> dict[str, dict]:
    path = _namespace_path(namespace)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    dirty = False
    for key in list(data):
        entry = data.get(key)
        if not isinstance(entry, dict) or _expired(entry):
            data.pop(key, None)
            dirty = True
    if dirty:
        _write_namespace(namespace, data)
    return data


def _write_namespace(namespace: str, data: dict[str, dict]) -> None:
    path = _namespace_file(namespace)
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def _migrate_legacy_memory() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if MIGRATION_MARKER.exists():
        return
    general = {}
    if MEMORY_FILE.exists():
        try:
            old = json.loads(MEMORY_FILE.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            old = {}
        for key, value in old.items():
            if isinstance(value, dict):
                stored = redact_text(str(value.get('value', '')))
                updated = str(value.get('updated', _now()))
            else:
                stored = redact_text(str(value))
                updated = _now()
            general[str(key)] = {'value': stored, 'updated': updated, 'expires': None}
    if general:
        _write_namespace('general', general)
    MIGRATION_MARKER.write_text(_now(), encoding='utf-8')


def memory_set(namespace: str, key: str, value: str, ttl_seconds: int = 0) -> None:
    data = _load_namespace(namespace)
    expires = None
    if ttl_seconds > 0:
        expires = time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime(time.time() + ttl_seconds))
    data[str(key)] = {'value': redact_text(value), 'updated': _now(), 'expires': expires}
    _write_namespace(namespace, data)


def memory_get(namespace: str, key: str) -> dict | None:
    data = _load_namespace(namespace)
    return data.get(str(key))


def memory_list(namespace: str = 'general', prefix: str = '') -> list[tuple[str, dict]]:
    data = _load_namespace(namespace)
    return [(key, data[key]) for key in sorted(data) if key.startswith(prefix)]


def memory_delete(namespace: str, key: str) -> bool:
    data = _load_namespace(namespace)
    existed = str(key) in data
    if existed:
        del data[str(key)]
        _write_namespace(namespace, data)
    return existed


def memory_search(namespace: str, query: str) -> list[tuple[str, dict]]:
    needle = str(query).lower()
    return [
        (key, entry)
        for key, entry in memory_list(namespace)
        if needle in key.lower() or needle in str(entry.get('value', '')).lower()
    ]
