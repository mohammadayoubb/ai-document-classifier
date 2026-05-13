# Collaboration

## Trello Board

https://trello.com/b/wvsbJtpF/ai-document-classifier

## Team Assignments

| Member | Primary Ownership |
|--------|------------------|
| **Jana Razzouk** | ML Classifier (Colab training) · Model artifacts · Golden-set selection · CI golden-set test |
| **Mohammad Ayoub** | Auth (fastapi-users + Vault) · Casbin RBAC · Audit log · User routes |
| **Alisar Al Musa** | Core API layer · Repositories · Services · Caching (fastapi-cache2) · Batch/Prediction routes |
| **Ali Hamad** | Docker Compose · SFTP ingest worker · Inference worker (RQ) · MinIO · Infra adapters · Frontend |

## How we handled merges and review

Each member worked on a dedicated feature branch (`feature/auth`, `feature/services-logic`,
`feature/workers`, `classifier`). Pull requests were opened against `main` and required at
least one reviewer before merging. We used GitHub PR comments to flag layer boundary violations
(e.g., cache calls in routes) and enforced the architecture contract from CLAUDE.md on every review.
Branches were deleted after merging to keep the branch list clean.

## Where we got stuck and how we unblocked

The hardest bug was in the RQ inference worker. The worker uses `asyncio.run()` to bridge
from RQ's synchronous job function into our async repositories and MinIO client. The original
code had two separate `asyncio.run()` calls — one for the main inference path and one for the
failure-marking path. When inference failed, the second `asyncio.run()` created a new event loop,
but the SQLAlchemy async engine was bound to the first loop, causing:

```
Future attached to a different loop
```

The fix was to merge both paths into a single `_async_job_with_cleanup()` coroutine so that
all async code runs in one event loop for the lifetime of the job. The lesson: one
`asyncio.run()` per job function — never two.

## One decision the team disagreed on

[Add one real disagreement the team had — e.g., RQ vs Celery, sync vs async repos,
whether to expose a direct upload endpoint, etc. Two or three sentences is enough.]
