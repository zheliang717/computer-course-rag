"""Initialize ONLY the independent, explicitly approved public preview copy."""
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password
from app.config import Settings
from app.model_config import ModelConfigService
from app.models import AuditLog, ModelQuota, User

root = Path('/provision')
marker = root / 'initialized.json'
if os.environ.get('ALLOW_FUNNEL_COPY_PROVISION') != 'yes':
    raise SystemExit('Preview provisioning not authorized.')
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as connection:
    if connection.scalar(text('select current_database()')) != 'rag_preview':
        raise SystemExit('Refusing to modify a non-preview database.')
if len(os.environ.get('PREVIEW_AUTH_SECRET', '')) < 64:
    raise SystemExit('Preview signing key is missing or weak.')
if marker.exists():
    print('Preview is already initialized. Existing passwords were not changed.')
    raise SystemExit(0)

factory = sessionmaker(bind=engine, expire_on_commit=False)
accounts_path = root / 'accounts.json'
if accounts_path.exists():
    accounts = json.loads(accounts_path.read_text(encoding='utf-8'))
else:
    with factory() as session:
        accounts = [dict(username=row.username, display_name=row.display_name,
                         role=row.role, active=row.active, password=secrets.token_urlsafe(24))
                    for row in session.scalars(select(User).order_by(User.username))]
    with accounts_path.open('x', encoding='utf-8') as stream:
        json.dump(accounts, stream, ensure_ascii=False, indent=2)
    accounts_path.chmod(0o600)
passwords = {row['username']: row['password'] for row in accounts}
if len(passwords) != len(accounts) or any(len(value) < 24 for value in passwords.values()):
    raise SystemExit('Invalid preview account manifest; refusing a partial reset.')

transfer_path = root / 'model-transfer.json'
transfer = json.loads(transfer_path.read_text(encoding='utf-8'))
with factory() as session:
    users = session.scalars(select(User)).all()
    if set(passwords) != {row.username for row in users}:
        raise SystemExit('Account manifest does not match the restored copy.')
    for row in users:
        row.password_hash = hash_password(passwords[row.username])
    for role, limit in {'student': 5, 'teacher': 10, 'admin': 20}.items():
        quota = session.get(ModelQuota, role)
        if quota:
            quota.daily_limit = min(quota.daily_limit, limit)
        else:
            session.add(ModelQuota(role=role, daily_limit=limit))
    session.add(AuditLog(actor_name='部署初始化', action='preview_hardening', resource_type='deployment',
                         resource_id='rag-funnel', detail={'account_count': len(users),
                         'passwords_rotated': True, 'independent_signing_key': True,
                         'source_database_modified': False, 'per_role_limits': [5, 10, 20]}))
    effective = Settings(_env_file=None, **transfer)
    service = ModelConfigService(factory, os.environ['MODEL_CONFIG_SECRET_PATH'])
    ciphertext = service.encrypt_key(effective.llm_api_key) if effective.llm_api_key else ''
    ModelConfigService.save_in_session(session, effective, ciphertext=ciphertext)
    session.commit()

result = {'initialized_at': datetime.now(timezone.utc).isoformat(), 'database': 'rag_preview',
          'users_rotated': len(accounts), 'model_configured': bool(effective.llm_api_key and effective.llm_provider != 'offline'),
          'embedding_provider': effective.embedding_provider, 'embedding_model': effective.embedding_model,
          'embedding_dimensions': effective.embedding_dimensions,
          'source_database_modified': False, 'quota_limits': {'student': 5, 'teacher': 10, 'admin': 20}}
with marker.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
transfer_path.unlink()
print(json.dumps(result, ensure_ascii=False))
