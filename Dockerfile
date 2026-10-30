FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir 'sentence-transformers>=3.0,<6'

COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY app/__init__.py ./app/__init__.py
RUN pip install --no-cache-dir .

COPY app ./app
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY scripts ./scripts
COPY materials/eval ./materials/eval
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
