from core.security import is_sensitive_path, redact_obj, redact_text


def test_api_key_redaction():
    assert '***REDACTED***' in redact_text('api_key=abcdefghijklmnop')


def test_password_redaction():
    assert '***REDACTED***' in redact_text('password=supersecret')


def test_token_redaction():
    assert '***REDACTED***' in redact_text('token=abcdefghijklmnop')


def test_nested_dict_redaction():
    value = redact_obj({'auth_token': 'abcdefghijklmnop', 'nested': {'password': 'supersecret'}})
    assert value['auth_token'] == '***REDACTED***'
    assert value['nested']['password'] == '***REDACTED***'


def test_sensitive_path_detection():
    assert is_sensitive_path('/tmp/.ssh/id_rsa')
