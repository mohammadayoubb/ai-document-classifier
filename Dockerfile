FROM python:3.11-slim AS base
WORKDIR /app
RUN pip install uv
COPY pyproject.toml uv.lock* ./
RUN uv pip install --system torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN uv pip install --system -r pyproject.toml

# Install dependencies first so this layer is cached across code changes
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.111.0" \
    "uvicorn[standard]>=0.29.0" \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.2.0" \
    "sqlalchemy[asyncio]>=2.0.0" \
    "asyncpg>=0.29.0" \
    "alembic>=1.13.0" \
    "fastapi-users[sqlalchemy]>=13.0.0" \
    "casbin>=1.36.0" \
    "casbin-sqlalchemy-adapter>=0.5.0" \
    "fastapi-cache2[redis]>=0.2.1" \
    "rq>=1.16.0" \
    "redis>=4.6.0,<5.0.0" \
    "hvac>=2.1.0" \
    "miniopy-async>=1.19.0" \
    "structlog>=24.1.0" \
    "paramiko>=3.4.0" \
    "pillow>=10.3.0" \
    "httpx>=0.27.0" \
    "psycopg2-binary>=2.9.9" \
    "email-validator>=2.1.0" \
    "tenacity>=8.2.0" \
    "python-multipart>=0.0.9"

# torch and torchvision are large — separate layer to keep rebuilds fast
RUN pip install --no-cache-dir "torch>=2.4.0" "torchvision>=0.19.0"

COPY alembic.ini ./
COPY app/ ./app/

FROM base AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
CMD ["python", "-m", "app.workers.inference"]

FROM base AS sftp-ingest
CMD ["python", "-m", "app.workers.ingest"]

FROM base AS migrate
CMD ["alembic", "upgrade", "head"]
