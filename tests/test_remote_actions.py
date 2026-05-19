import pytest

from core.remote_actions import build_remote_command


def test_known_action_builds_command():
    cmd = build_remote_command('docker_ps', remote_path='/srv/app')
    assert 'docker compose ps' in cmd


def test_unknown_action_rejected():
    with pytest.raises(ValueError):
        build_remote_command('rm_all')


def test_docker_logs_limits_lines():
    cmd = build_remote_command('docker_logs', remote_path='/srv/app', service='web', lines=999)
    assert '--tail 200' in cmd


def test_suspicious_service_name_rejected():
    with pytest.raises(ValueError):
        build_remote_command('docker_logs', remote_path='/srv/app', service='web; rm -rf /')


def test_remote_path_required():
    with pytest.raises(ValueError):
        build_remote_command('docker_ps')
