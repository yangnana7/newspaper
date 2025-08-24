import os


def test_env_fixed_values_using_monkeypatch(monkeypatch):
    # Simulate CI/.env loading
    monkeypatch.setenv('APP_BIND_HOST', '127.0.0.1')
    monkeypatch.setenv('APP_BIND_PORT', '3011')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://127.0.0.1/newshub')

    assert os.environ.get('APP_BIND_HOST') == '127.0.0.1'
    assert os.environ.get('APP_BIND_PORT') == '3011'
    assert '/newshub' in os.environ.get('DATABASE_URL', '')

