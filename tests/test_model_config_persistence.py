"""Model settings survive a new service instance; credentials stay encrypted."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.model_config import ModelConfigService
from app.database import Base
from app.models import AuditLog, ModelRuntimeConfig, User


def test_model_config_round_trip_with_encrypted_key(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    ModelRuntimeConfig.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    key_path = tmp_path / "model-config.key"
    service = ModelConfigService(sessions, str(key_path))
    environment = Settings(_env_file=None, llm_provider="offline", llm_api_key="environment-key")
    assert service.load(environment).llm_provider == "offline"

    configured = environment.model_copy(deep=True)
    configured.llm_provider = "compatible"
    configured.llm_model = "course-model"
    configured.llm_api_key = "private-provider-key"
    configured.retrieval_top_k = 7
    service.save(configured, api_key_changed=True)

    with sessions() as session:
        saved = session.get(ModelRuntimeConfig, 1)
        assert saved is not None
        assert saved.api_key_ciphertext is not None
        assert "private-provider-key" not in saved.api_key_ciphertext
    assert key_path.is_file()

    restarted = ModelConfigService(sessions, str(key_path)).load(environment)
    assert restarted.llm_provider == "compatible"
    assert restarted.llm_model == "course-model"
    assert restarted.llm_api_key == "private-provider-key"
    assert restarted.retrieval_top_k == 7
    assert environment.llm_provider == "offline"

    restarted.llm_model = "next-model"
    service.save(restarted, api_key_changed=False)
    again = ModelConfigService(sessions, str(key_path)).load(environment)
    assert again.llm_model == "next-model"
    assert again.llm_api_key == "private-provider-key"


def test_new_key_cannot_be_persisted_without_secret_path(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    ModelRuntimeConfig.__table__.create(engine)
    service = ModelConfigService(sessionmaker(bind=engine), None)
    configured = Settings(_env_file=None, llm_api_key="new-key")
    try:
        service.save(configured, api_key_changed=True)
    except ValueError as exc:
        assert "密钥路径" in str(exc)
    else:
        raise AssertionError("保存新的 API Key 必须需要独立的加密密钥")


def test_model_config_and_audit_commit_or_roll_back_together(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    actor_id = uuid4()
    with sessions.begin() as session:
        session.add(User(id=actor_id, username="model_admin", display_name="模型管理员",
                         role="admin", active=True, password_hash="x"))
    service = ModelConfigService(sessions, str(tmp_path / "model-config.key"))
    settings = Settings(_env_file=None, llm_provider="offline", llm_api_key="")
    service.save(settings, api_key_changed=False)
    candidate = settings.model_copy(deep=True)
    candidate.llm_model = "new-model"

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit storage failed")

    event.listen(AuditLog, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit storage failed"):
            service.save(candidate, api_key_changed=False,
                         actor_id=actor_id, actor_name="模型管理员")
    finally:
        event.remove(AuditLog, "before_insert", fail_audit)
    with sessions() as session:
        assert session.get(ModelRuntimeConfig, 1).model == settings.llm_model
        assert list(session.scalars(select(AuditLog)).all()) == []

    service.save(candidate, api_key_changed=False, actor_id=actor_id, actor_name="模型管理员")
    with sessions() as session:
        assert session.get(ModelRuntimeConfig, 1).model == "new-model"
        audit = session.scalar(select(AuditLog))
        assert audit is not None and audit.resource_type == "model_config"
        assert audit.detail["model"] == "new-model" and audit.detail["confirmed"] is True
