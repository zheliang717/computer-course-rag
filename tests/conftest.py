"""Keep deterministic unit tests independent of the developer's live .env."""

import os
import sys
from uuid import uuid4
import pytest

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


# Imported by pytest before test modules import app.main and cache Settings.
# Live API tests talk to the already-running server and are unaffected here.
os.environ.update({
    "EMBEDDING_PROVIDER": "hashing",
    "LLM_PROVIDER": "offline",
    "AUTH_REQUIRED": "false",
    "ASSISTANT_TASK_WORKER_ENABLED": "false",
})


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite_test(element, compiler, **kwargs):
    del element, compiler, kwargs
    return "JSON"


@pytest.fixture(autouse=True)
def isolated_request_window(monkeypatch):
    # Tests are independent users/scenarios, not one process-wide burst of logins.
    module = sys.modules.get('app.main')
    if module is not None:
        from app.security import SlidingWindowRateLimiter
        monkeypatch.setattr(module, 'rate_limiter', SlidingWindowRateLimiter())


@pytest.fixture
def postgres_sessions():
    """Real JSONB/permission semantics in a named disposable DB and unique schema."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    url = os.environ.get('FULL_TEST_DATABASE_URL')
    if not url: pytest.skip('requires explicit disposable PostgreSQL FULL_TEST_DATABASE_URL')
    assert make_url(url).database == 'rag_full_tests_20261028'
    schema = 'test_' + uuid4().hex
    control = create_engine(url)
    with control.begin() as conn: conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema},public'})
    try:
        Base.metadata.create_all(engine)
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with control.begin() as conn: conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        control.dispose()
