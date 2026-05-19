import time

import pytest

from core.memory_store import memory_delete, memory_get, memory_list, memory_set, normalize_namespace


def test_set_get_namespace():
    memory_set('pytest', 'key', 'value')
    assert memory_get('pytest', 'key')['value'] == 'value'


def test_list_prefix():
    memory_set('pytest', 'prefix-one', 'value')
    rows = memory_list('pytest', 'prefix-')
    assert any(key == 'prefix-one' for key, _ in rows)


def test_delete():
    memory_set('pytest', 'delete-me', 'value')
    assert memory_delete('pytest', 'delete-me') is True


def test_ttl_expiry():
    memory_set('pytest', 'ttl-key', 'value', ttl_seconds=1)
    time.sleep(2)
    assert memory_get('pytest', 'ttl-key') is None


def test_namespace_validation():
    with pytest.raises(ValueError):
        normalize_namespace('Bad Namespace')
