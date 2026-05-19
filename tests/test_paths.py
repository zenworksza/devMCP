from pathlib import Path

import pytest

from core.paths import UnsafePathError, safe_new_project_name, safe_project_file, safe_project_path
from core.runtime import PROJECT_ROOT


def setup_module(module):
    (PROJECT_ROOT / 'sample' / 'src').mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / 'sample' / '.env').write_text('TOKEN=x', encoding='utf-8')
    (PROJECT_ROOT / 'sample' / 'src' / 'main.py').write_text('print(1)\n', encoding='utf-8')


def test_safe_project_path_resolves_under_root():
    path = safe_project_path('sample')
    assert path == (PROJECT_ROOT / 'sample').resolve()


def test_parent_project_rejected():
    with pytest.raises(UnsafePathError):
        safe_project_path('../sample')


def test_absolute_project_rejected():
    with pytest.raises(UnsafePathError):
        safe_project_path('/tmp/sample')


def test_parent_file_rejected():
    with pytest.raises(UnsafePathError):
        safe_project_file('sample', '../x.txt')


def test_sensitive_file_rejected_by_default():
    with pytest.raises(UnsafePathError):
        safe_project_file('sample', '.env', must_exist=True)


def test_sensitive_file_allowed_with_flag():
    assert safe_project_file('sample', '.env', must_exist=True, allow_sensitive=True).name == '.env'


def test_new_project_name_rejects_parent():
    with pytest.raises(UnsafePathError):
        safe_new_project_name('../foo')
