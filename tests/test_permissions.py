import pytest

from core.permissions import PermissionDenied, check_permission


def test_allow_passes(monkeypatch):
    monkeypatch.setattr('core.permissions.load_policy', lambda: {'read': 'allow'})
    check_permission('read', tool='x')


def test_deny_raises(monkeypatch):
    monkeypatch.setattr('core.permissions.load_policy', lambda: {'read': 'deny'})
    with pytest.raises(PermissionDenied):
        check_permission('read', tool='x')


def test_prompt_without_confirm_raises(monkeypatch):
    monkeypatch.setattr('core.permissions.load_policy', lambda: {'write': 'prompt'})
    with pytest.raises(PermissionDenied):
        check_permission('write', tool='x')


def test_prompt_with_confirm_passes(monkeypatch):
    monkeypatch.setattr('core.permissions.load_policy', lambda: {'write': 'prompt'})
    check_permission('write', tool='x', confirm=True)
