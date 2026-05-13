# AI Document Classifier

**Week 6 Project — AIE Program**
**Team:** Jana Razzouk · Mohammad Ayoub · Alisar Al Musa · Ali Hamad

An internal document classification service that runs fully via `docker compose up`.
A scanner vendor drops TIFF images via SFTP; a ConvNeXt worker pipeline classifies them;
authenticated users browse and review results through a permission-gated API.

---

## Submission

| Field | Value |
|-------|-------|
| **Repo** | https://github.com/mohammadayoubb/ai-document-classifier |
| **Trello** | https://trello.com/b/wvsbJtpF/ai-document-classifier |
| **Tag** | `v0.1.0-week6` |
| **Backbone** | ConvNeXt Tiny — `ConvNeXt_Tiny_Weights.IMAGENET1K_V1` |
| **Freeze policy** | Partial unfreeze |
| **Test top-1** | 85.29% |
| **Test top-5** | 97.34% |
| **Worst class** | 72.78% — `scientific_report` |
| **Latency p95** | API cached < 50 ms · API uncached < 200 ms · Inference < 1.0 s · E2E < 10 s |

---

## Quick Start

```bash
git clone <repo-url>
cd ai-document-classifier
cp .env.example .env
docker compose up --build
```

The stack starts 9 services. When all are healthy, the API is at `http://localhost:8000`
and the frontend dashboard is at `http://localhost:5173`.

---

## Stack

| Service | Image | Purpose |
|---------|-------|---------|
| `api` | our build | FastAPI REST API (port 8000) |
| `worker` | our build | RQ inference worker |
| `sftp-ingest` | our build | SFTP file poller |
| `migrate` | our build | Alembic migrations (runs and exits) |
| `db` | postgres:16 | Application database |
| `redis` | redis:7-alpine | Job queue + API cache |
| `minio` | minio/minio | Object storage (port 9000, console 9001) |
| `sftp` | atmoz/sftp | SFTP drop zone (port 2222) |
| `vault` | hashicorp/vault:1.16 | Secret store — dev mode (port 8200) |
| `frontend` | our build | React + Vite dashboard (port 5173) |

---

## Model

- **Architecture:** ConvNeXt Tiny, pretrained on ImageNet-1K
- **Dataset:** RVL-CDIP — 16 document layout classes, 320k train / 40k val / 40k test
- **Task:** Visual layout classification — no OCR, no text reading
- **Training:** AdamW, lr=1e-4, CosineAnnealingLR, partial unfreeze, 3 epochs (early stopping)
- **Weights:** `app/classifier/models/classifier.pt` (106 MB, tracked via git LFS)
- **Model card:** `app/classifier/models/model_card.json`

### 16 Classes

`letter` · `form` · `email` · `handwritten` · `advertisement` · `scientific_report` ·
`scientific_publication` · `specification` · `file_folder` · `news_article` · `budget` ·
`invoice` · `presentation` · `questionnaire` · `resume` · `memo`

---

## Roles

| Role | Permissions |
|------|------------|
| `admin` | Invite users, toggle roles, view audit log |
| `reviewer` | View batches, relabel predictions where confidence < 0.7 |
| `auditor` | Read-only on batches and audit log |

---

## Documentation

- [ARCH.md](ARCH.md) — Container diagram, data flow, layer boundaries, secrets, cache, queue
- [DECISIONS.md](DECISIONS.md) — Every non-obvious architectural decision with rationale
- [RUNBOOK.md](RUNBOOK.md) — Step-by-step operations: start, seed, test, swap model, teardown
- [SECURITY.md](SECURITY.md) — Secrets management, JWT, CORS, threat model
- [COLLABORATION.md](COLLABORATION.md) — Team assignments, Trello, collaboration notes

---

## Latency Budgets

Committed targets (demonstrated in demo):

| Metric | Budget | How measured |
|--------|--------|--------------|
| API cached reads (p95) | < 50 ms | `GET /batches` with warm Redis cache |
| API uncached reads (p95) | < 200 ms | `GET /batches` after cache flush |
| Inference per document (p95) | < 1.0 s | CPU, ConvNeXt Tiny, single document |
| End-to-end (SFTP drop → API) | < 10 s | `docker cp` → `GET /batches/{id}` = completed |
