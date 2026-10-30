import base64
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthService, LOGIN_SECONDS, REMEMBER_LOGIN_SECONDS


@pytest.fixture
def login_client(monkeypatch):
    from app import main
    service = AuthService(None, secret='isolated-login-test', required=True)
    monkeypatch.setattr(main, 'auth', service)
    monkeypatch.setattr(main, 'security_service', None)
    monkeypatch.setattr(main, 'account_guard', SimpleNamespace(
        check=lambda *args: None, success=lambda *args: None, failed=lambda *args: None))
    return TestClient(main.app), service


def decode_payload(token):
    value = token.split('.')[0]
    return json.loads(base64.urlsafe_b64decode(value + '=' * (-len(value) % 4)))


@pytest.mark.parametrize('role', ['student', 'teacher', 'admin'])
@pytest.mark.parametrize('remember', [False, True])
def test_role_login_has_server_selected_lifetime(login_client, role, remember):
    client, service = login_client
    before = int(time.time())
    response = client.post('/api/v1/auth/login', json={
        'username': role, 'password': role + '123', 'remember_me': remember})
    assert response.status_code == 200
    data = response.json()
    lifetime = REMEMBER_LOGIN_SECONDS if remember else LOGIN_SECONDS
    assert data['remember_me'] is remember and data['expires_in'] == lifetime
    assert before + lifetime <= decode_payload(data['access_token'])['exp'] <= int(time.time()) + lifetime
    assert service.verify_token(data['access_token']).role == role
    assert client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + data['access_token']}).status_code == 200


def test_legacy_login_defaults_to_eight_hours(login_client):
    client, _ = login_client
    response = client.post('/api/v1/auth/login', json={'username': 'student', 'password': 'student123'})
    assert response.status_code == 200
    assert response.json()['expires_in'] == LOGIN_SECONDS
    assert response.json()['remember_me'] is False


@pytest.mark.parametrize('invalid', ['true', 7, None, {}])
def test_remember_flag_cannot_accept_arbitrary_duration(login_client, invalid):
    client, _ = login_client
    assert client.post('/api/v1/auth/login', json={
        'username': 'student', 'password': 'student123', 'remember_me': invalid}).status_code == 422


def test_seven_day_token_has_fixed_not_sliding_expiry(monkeypatch):
    service = AuthService(None, secret='isolated-seven-day', required=True)
    principal = service.authenticate('student', 'student123')
    clock = [2_000_000_000]
    monkeypatch.setattr('app.auth.time.time', lambda: clock[0])
    normal = service.issue_token(principal)
    remembered = service.issue_token(principal, expires_in=REMEMBER_LOGIN_SECONDS)
    original_exp = decode_payload(remembered)['exp']
    clock[0] += LOGIN_SECONDS
    assert service.verify_token(normal) is None
    assert service.verify_token(remembered) is not None
    clock[0] = original_exp - 1
    assert service.verify_token(remembered) is not None
    assert decode_payload(remembered)['exp'] == original_exp
    clock[0] = original_exp
    assert service.verify_token(remembered) is None


def test_modified_expiry_and_wrong_password_are_rejected(login_client):
    client, service = login_client
    assert client.post('/api/v1/auth/login', json={
        'username': 'student', 'password': 'wrong', 'remember_me': True}).status_code == 401
    token = service.issue_token(service.authenticate('student', 'student123'))
    payload = decode_payload(token)
    payload['exp'] += REMEMBER_LOGIN_SECONDS
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    assert service.verify_token(encoded + '.' + token.split('.')[1]) is None
