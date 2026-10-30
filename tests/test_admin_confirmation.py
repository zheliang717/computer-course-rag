"""Dangerous admin changes require explicit confirmation and remain audited."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import main as main_module


client = TestClient(main_module.app)


class FakeAdminService:
    def __init__(self) -> None:
        self.changes: list[tuple[str, bool]] = []
        self.audits: list[dict] = []

    def set_user_active(self, user_id, active, **audit):
        self.changes.append((str(user_id), active))
        self.add_audit(action="activate" if active else "deactivate",
                       detail={"confirmed": audit["confirmed"]})
        return {
            "id": str(user_id), "username": "example", "display_name": "测试账号",
            "role": "student", "active": active, "created_at": None,
        }

    def add_audit(self, **kwargs):
        self.audits.append(kwargs)


def _admin_headers() -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_user_deactivation_requires_confirmation_and_writes_audit(monkeypatch) -> None:
    service = FakeAdminService()
    monkeypatch.setattr(main_module, "admin_service", service)
    user_id = str(uuid4())
    headers = _admin_headers()

    rejected = client.patch(f"/api/v1/admin/users/{user_id}", headers=headers, json={"active": False})
    assert rejected.status_code == 409
    assert service.changes == []
    assert service.audits == []

    accepted = client.patch(f"/api/v1/admin/users/{user_id}", headers=headers, json={
        "active": False, "confirmed": True,
    })
    assert accepted.status_code == 200
    assert accepted.json()["active"] is False
    assert service.changes == [(user_id, False)]
    assert service.audits[0]["action"] == "deactivate"
    assert service.audits[0]["detail"]["confirmed"] is True


def test_model_config_requires_confirmation_and_audits_accepted_change(monkeypatch) -> None:
    service = FakeAdminService()
    monkeypatch.setattr(main_module, "admin_service", service)
    monkeypatch.setattr(main_module, "settings", main_module.settings.model_copy(deep=True))
    monkeypatch.setattr(main_module, "generator", main_module.generator)
    monkeypatch.setattr(main_module, "retrieval", main_module.retrieval)
    headers = _admin_headers()
    before = client.get("/api/v1/admin/model-config", headers=headers).json()
    payload = {
        "provider": "offline", "model": "different-model", "api_base": before["api_base"],
        "timeout_seconds": before["timeout_seconds"], "fallback_offline": before["fallback_offline"],
        "retrieval_top_k": before["retrieval_top_k"],
        "retrieval_min_score": before["retrieval_min_score"],
        "retrieval_vector_weight": before["retrieval_vector_weight"],
    }

    rejected = client.put("/api/v1/admin/model-config", headers=headers, json=payload)
    assert rejected.status_code == 409
    assert client.get("/api/v1/admin/model-config", headers=headers).json() == before
    assert service.audits == []

    accepted = client.put("/api/v1/admin/model-config", headers=headers, json={
        **payload, "confirmed": True,
    })
    assert accepted.status_code == 200
    assert accepted.json()["model"] == "different-model"
    assert service.audits[0]["resource_type"] == "model_config"
    assert service.audits[0]["detail"]["confirmed"] is True


def test_student_cannot_confirm_admin_change() -> None:
    login = client.post("/api/v1/auth/login", json={"username": "student", "password": "student123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.patch(f"/api/v1/admin/users/{uuid4()}", headers=headers, json={
        "active": False, "confirmed": True,
    })
    assert response.status_code == 403


def test_model_config_does_not_switch_runtime_when_persistence_fails(monkeypatch) -> None:
    class FailingModelConfigService:
        def load(self, baseline, **kwargs):
            return baseline
        def save(self, *_args, **_kwargs):
            raise RuntimeError("audit storage failed")

    monkeypatch.setattr(main_module, "model_config_service", FailingModelConfigService())
    before_settings = main_module.settings
    before_generator = main_module.generator
    before_retrieval = main_module.retrieval
    headers = _admin_headers()
    payload = {
        "provider": "offline", "model": "must-not-become-active", "api_base": before_settings.llm_api_base,
        "timeout_seconds": before_settings.llm_timeout_seconds,
        "fallback_offline": before_settings.llm_fallback_offline,
        "retrieval_top_k": before_settings.retrieval_top_k,
        "retrieval_min_score": before_settings.retrieval_min_score,
        "retrieval_vector_weight": before_settings.retrieval_vector_weight,
        "confirmed": True,
    }
    with pytest.raises(RuntimeError, match="audit storage failed"):
        client.put("/api/v1/admin/model-config", headers=headers, json=payload)
    assert main_module.settings is before_settings
    assert main_module.generator is before_generator
    assert main_module.retrieval is before_retrieval
