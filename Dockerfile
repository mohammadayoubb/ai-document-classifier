FROM python:3.11-slim AS base
WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock* ./

# Install CPU-only torch first so the separate index URL is applied before uv
# resolves the rest of the dependencies (which include torch as a dep too).
RUN uv pip install --system torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install remaining application dependencies from pyproject.toml.
RUN uv pip install --system -r pyproject.toml

COPY alembic.ini ./
COPY app/ ./app/
COPY scripts/ ./scripts/

FROM base AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
CMD ["python", "-m", "app.workers.inference"]

FROM base AS sftp-ingest
CMD ["python", "-m", "app.workers.ingest"]

FROM base AS migrate
CMD ["alembic", "upgrade", "head"]
