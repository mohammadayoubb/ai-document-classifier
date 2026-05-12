FROM python:3.11-slim AS base
WORKDIR /app
RUN pip install uv
COPY pyproject.toml uv.lock* ./
RUN uv pip install --system torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN uv pip install --system -r pyproject.toml

COPY app/ ./app/

FROM base AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
CMD ["python", "-m", "app.workers.inference"]

FROM base AS sftp-ingest
CMD ["python", "-m", "app.workers.ingest"]

FROM base AS migrate
CMD ["alembic", "upgrade", "head"]
