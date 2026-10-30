from app.auth import AuthService, verify_password


def test_password_hash_and_local_token_round_trip() -> None:
    service = AuthService(None, secret="test-secret", required=True)
    principal = service.authenticate("teacher", "teacher123")
    assert principal is not None
    assert verify_password("teacher123", "pbkdf2_sha256$1$00$00") is False
    token = service.issue_token(principal)
    restored = service.verify_token(token)
    assert restored is not None
    assert restored.username == "teacher"
    assert restored.role == "teacher"


def test_local_auth_rejects_wrong_password() -> None:
    service = AuthService(None, secret="test-secret", required=True)
    assert service.authenticate("student", "wrong") is None
