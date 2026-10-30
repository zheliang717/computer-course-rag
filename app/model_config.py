"""Durable model settings with a separate, local encryption key for credentials."""

from __future__ import annotations

import os
import hmac
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.models import AuditLog, ModelRuntimeConfig
from app.schemas import ModelConfigValues


class ModelConfigService:
    def __init__(self, session_factory, secret_path: str | None) -> None:
        self._session_factory = session_factory
        self._secret_path = Path(secret_path) if secret_path else None

    def _cipher(self, *, create: bool) -> Fernet:
        if self._secret_path is None:
            raise ValueError("尚未配置持久化模型密钥路径，不能保存新的 API Key。")
        if create:
            self._secret_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(self._secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(Fernet.generate_key())
                    stream.flush()
                    os.fsync(stream.fileno())
        try:
            key = self._secret_path.read_bytes().strip()
            return Fernet(key)
        except (OSError, ValueError) as exc:
            raise ValueError("模型配置加密密钥不可用。请检查持久化密钥卷。") from exc

    def load(self, environment_settings, *, allow_credential_failure=False):
        """Apply saved fields over environment defaults without exposing credentials."""
        with self._session_factory() as session:
            return self.load_in_session(session, environment_settings, allow_credential_failure=allow_credential_failure)

    def load_in_session(self, session, baseline, *, allow_credential_failure=False):
        row = session.get(ModelRuntimeConfig, 1)
        effective = baseline.model_copy(deep=True)
        if row is not None:
            for field in ("provider", "model", "api_base", "timeout_seconds", "fallback_offline"):
                setattr(effective, "llm_" + field, getattr(row, field))
            for field in ("retrieval_top_k", "retrieval_min_score", "retrieval_vector_weight"):
                setattr(effective, field, getattr(row, field))
            if row.api_key_ciphertext:
                try:
                    effective.llm_api_key = self.decrypt_key(row.api_key_ciphertext)
                except ValueError:
                    if not allow_credential_failure and effective.llm_provider != "offline":
                        raise
                    effective.llm_api_key = None
        return effective

    def encrypt_key(self, value: str) -> str:
        if not value.strip():
            raise ValueError("新的 API Key 不能为空。")
        return self._cipher(create=True).encrypt(value.strip().encode("utf-8")).decode("ascii")

    def decrypt_key(self, ciphertext: str) -> str:
        try:
            return self._cipher(create=False).decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError) as exc:
            raise ValueError("模型配置加密密钥不可用或与已保存数据不匹配。") from exc

    @staticmethod
    def public_values(effective) -> dict:
        return {"provider": effective.llm_provider, "model": effective.llm_model,
            "api_base": effective.llm_api_base, "timeout_seconds": effective.llm_timeout_seconds,
            "fallback_offline": effective.llm_fallback_offline, "retrieval_top_k": effective.retrieval_top_k,
            "retrieval_min_score": effective.retrieval_min_score, "retrieval_vector_weight": effective.retrieval_vector_weight,
            "configured": effective.llm_provider != "offline" and bool(effective.llm_api_key)}

    @classmethod
    def same_settings(cls, left, right):
        return cls.public_values(left) == cls.public_values(right) and hmac.compare_digest(
            (left.llm_api_key or "").encode(), (right.llm_api_key or "").encode())

    @staticmethod
    def candidate(baseline, values: dict):
        validated = ModelConfigValues.model_validate(values)
        model = validated.model.strip()
        base = validated.api_base.strip().rstrip("/")
        parsed = urlsplit(base)
        if not model:
            raise ValueError("模型名称不能为空。")
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("接口地址须为不含登录信息、查询参数或片段的 HTTP(S) 基础地址；密钥请填入独立密码框。")
        effective = baseline.model_copy(deep=True)
        effective.llm_provider, effective.llm_model, effective.llm_api_base = validated.provider, model, base
        if validated.api_key and validated.api_key.strip():
            effective.llm_api_key = validated.api_key.strip()
        effective.llm_timeout_seconds, effective.llm_fallback_offline = validated.timeout_seconds, validated.fallback_offline
        effective.retrieval_top_k, effective.retrieval_min_score = validated.retrieval_top_k, validated.retrieval_min_score
        effective.retrieval_vector_weight = validated.retrieval_vector_weight
        if effective.llm_provider != "offline" and not effective.llm_api_key:
            raise ValueError("在线模型需要有效的 API Key，当前未提供且没有可保留的密钥。")
        return effective

    def save(self, effective_settings, *, api_key_changed: bool,
             actor_id: UUID | None = None, actor_name: str | None = None) -> None:
        ciphertext = self.encrypt_key(effective_settings.llm_api_key or "") if api_key_changed else None
        with self._session_factory() as session:
            self.save_in_session(session, effective_settings, ciphertext=ciphertext,
                actor_id=actor_id, actor_name=actor_name)
            session.commit()

    @staticmethod
    def save_in_session(session, effective, *, ciphertext=None, actor_id=None, actor_name=None,
                        reason=None, operation_id=None):
        row = session.scalar(select(ModelRuntimeConfig).where(ModelRuntimeConfig.id == 1).with_for_update())
        if row is None:
            row = ModelRuntimeConfig(id=1)
            session.add(row)
        for field in ("provider", "model", "api_base", "timeout_seconds", "fallback_offline"):
            setattr(row, field, getattr(effective, "llm_" + field))
        for field in ("retrieval_top_k", "retrieval_min_score", "retrieval_vector_weight"):
            setattr(row, field, getattr(effective, field))
        if ciphertext is not None:
            row.api_key_ciphertext = ciphertext
        if actor_name is not None:
            session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action="update", resource_type="model_config",
                detail={**ModelConfigService.public_values(effective), "api_key_changed": ciphertext is not None, "confirmed": True,
                    **({"reason": reason} if reason else {}),
                    **({"assistant_operation_id": operation_id} if operation_id else {})}))
