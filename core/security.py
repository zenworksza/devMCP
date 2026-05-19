from __future__ import annotations

import re
from typing import Any

SECRET_PATTERNS = [
    re.compile(r'(?i)(aws_access_key_id\s*[=:]\s*)([A-Z0-9]{16,})'),
    re.compile(r'(?i)(aws_secret_access_key\s*[=:]\s*)([A-Za-z0-9/+=]{20,})'),
    re.compile(r'(?i)(openai_api_key\s*[=:]\s*)(sk-[A-Za-z0-9_\-]{20,})'),
    re.compile(r'(?i)(api[_-]?key\s*[=:]\s*)([\'\"]?[^\'\"\s]{12,}[\'\"]?)'),
    re.compile(r'(?i)(secret\s*[=:]\s*)([\'\"]?[^\'\"\s]{12,}[\'\"]?)'),
    re.compile(r'(?i)(token\s*[=:]\s*)([\'\"]?[^\'\"\s]{12,}[\'\"]?)'),
    re.compile(r'(?i)(password\s*[=:]\s*)([\'\"]?[^\'\"\s]{8,}[\'\"]?)'),
    re.compile(r'(?i)(passwd\s*[=:]\s*)([\'\"]?[^\'\"\s]{8,}[\'\"]?)'),
    re.compile(r'(?i)(authorization:\s*bearer\s+)([A-Za-z0-9._\-]{12,})'),
    re.compile(r'(?i)(x-api-key:\s*)([A-Za-z0-9._\-]{12,})'),
]

SENSITIVE_FILENAMES = {
    '.env',
    '.env.local',
    '.env.production',
    '.env.prod',
    'id_rsa',
    'id_ed25519',
    'known_hosts',
}


def redact_text(value: str) -> str:
    text = str(value)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}***REDACTED***", text)
    return text


def redact_obj(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_obj(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_obj(item) for item in value)
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            key_s = str(key)
            if re.search(r'(?i)(password|passwd|token|secret|api[_-]?key|authorization|private[_-]?key)', key_s):
                redacted[key] = '***REDACTED***'
            else:
                redacted[key] = redact_obj(item)
        return redacted
    return value


def is_sensitive_path(path: str) -> bool:
    normalized = str(path).replace('\\', '/')
    name = normalized.rsplit('/', 1)[-1]
    if name in SENSITIVE_FILENAMES:
        return True
    if normalized.endswith('/.ssh/config'):
        return True
    if '/.ssh/' in normalized:
        return True
    return False
