## Member C Implementation Guide — Core API Layer, Repositories, Services, Caching, Batch/Prediction Routes

## Your Ownership
### for any part realted to api routes, if something is missing alert this to me, to do not create it yourself, this is not my part, this will introduce a conflict

### if any part outside the scope of my dedicated part is missing, alert it to me, without changing anything yourself.
this is my part: 
Person 3 — DB/Services
- SQLAlchemy
- Alembic
- repositories
- infra
- services
- cache
- Vault
This is another description of my role: Member C:	Core API layer · Repositories · Services · Caching · Batch/Prediction routes


#### if something yoi think will be conflicted with member B, then alert it to me to decide before implementation ( especially in API routes part)
#### If some of the methods you found their skeleton there then you decide either to implement them or delete them if they will not be needed.
#### If some of the methods skeleton conflict with what is here, you choose the best one and implement it 
#### if something missing here you think it should be in my part, then tell me about it to discuss if implementing it or not. 

You own the backend core around:

- Batch service
- Prediction service
- Repository layer for batches/documents/predictions
- Cache service and cache invalidation
- Clean API → Service → Repository boundaries
- Returning API-ready responses for batches and predictions

You are NOT the owner of:
- ML training
- classifier.pt
- SFTP polling worker
- MinIO low-level adapter
- API Auth implementation internals
- Casbin policy setup
- Vault setup
- Docker/CI ownership

But your code must integrate cleanly with all of them.

---

## Your Main Goal

Build the API/service/repository core that lets authenticated users:

1. List document batches.
2. View one batch with its documents and predictions.
3. View recent predictions.
4. Relabel low-confidence predictions.
5. Ensure cache is used for reads and invalidated on writes.
6. Keep all business logic in services.
7. Keep all SQL in repositories.
8. Keep routes thin.

---

## Required Architecture Rule

Use this dependency direction:

```text
API routes
↓
Services
↓              ↓
Repositories   Infra adapters
↓              ↓
Postgres       Redis/cache/MinIO/etc.
```

Never do this:

```text
route → SQLAlchemy directly
route → Redis directly
repository → cache
repository → HTTPException
repository → MinIO
```

Correct:

```text
route → service → repository → Postgres
route → service → cache service → Redis
```

---

## Files You Should Create / Own

Recommended file list:

```text
app/api/routers/batches.py
app/api/routers/predictions.py

app/services/batch_service.py
app/services/prediction_service.py
app/services/cache_service.py

app/repositories/batch_repository.py
app/repositories/document_repository.py
app/repositories/prediction_repository.py

app/domain/batch.py
app/domain/document.py
app/domain/prediction.py
app/domain/pagination.py

tests/services/test_batch_service.py
tests/services/test_prediction_service.py
tests/repositories/test_batch_repository.py
tests/api/test_batches_routes.py
tests/api/test_predictions_routes.py
```

Optional, if the team does not already have them:

```text
app/api/deps.py
app/core/exceptions.py
app/core/pagination.py
```

---

## Expected Route Files

## 1. app/api/routers/batches.py

Routes:

```text
GET /batches
GET /batches/{batch_id}
```

Purpose:

### GET /batches

Returns list of batches.

Should support optional query params:

```text
status
limit
offset
```

Example response idea:

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "batch_001",
      "status": "completed",
      "document_count": 3,
      "prediction_count": 3,
      "needs_review_count": 1,
      "created_at": "..."
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 100
}
```

Flow:

```text
route
↓
BatchService.list_batches()
↓
cache lookup
↓
BatchRepository.list_batches()
↓
Postgres
↓
cache set
↓
return response
```

### GET /batches/{batch_id}

Returns one batch with documents and predictions.

Example response idea:

```json
{
  "id": "uuid",
  "name": "batch_001",
  "status": "completed",
  "documents": [
    {
      "id": "uuid",
      "original_filename": "invoice_001.tiff",
      "status": "predicted",
      "blob_key": "originals/batch_001/invoice_001.tiff",
      "overlay_blob_key": "overlays/batch_001/invoice_001.png",
      "prediction": {
        "id": "uuid",
        "predicted_label": "invoice",
        "top1_confidence": 0.91,
        "top5_labels": ["invoice", "form", "letter", "memo", "email"],
        "needs_review": false,
        "corrected_label": null
      }
    }
  ]
}
```

Flow:

```text
route
↓
BatchService.get_batch_detail()
↓
cache lookup
↓
BatchRepository.get_batch_detail()
↓
Postgres
↓
cache set
↓
return response
```

Route responsibilities:

- Accept request.
- Get current user from dependency.
- Call service.
- Convert service errors to HTTP errors if needed.
- Return Pydantic response.

Route should NOT:

- Write SQL.
- Build cache keys.
- Run permission logic manually.
- Touch Redis directly.

---

## 2. app/api/routers/predictions.py

Routes:

```text
GET /predictions/recent
PATCH /predictions/{prediction_id}/relabel
```

### GET /predictions/recent

Returns recent predictions.

Should support:

```text
limit
only_needs_review=true/false
```

Example response:

```json
{
  "items": [
    {
      "id": "uuid",
      "document_id": "uuid",
      "batch_id": "uuid",
      "original_filename": "invoice_001.tiff",
      "predicted_label": "invoice",
      "top1_confidence": 0.64,
      "needs_review": true,
      "corrected_label": null,
      "created_at": "..."
    }
  ]
}
```

Flow:

```text
route
↓
PredictionService.get_recent_predictions()
↓
cache lookup
↓
PredictionRepository.get_recent_predictions()
↓
Postgres
↓
cache set
↓
return response
```

### PATCH /predictions/{prediction_id}/relabel

Reviewer corrects a low-confidence prediction.

Request body:

```json
{
  "corrected_label": "form"
}
```

Business rule:

```text
Only reviewer/admin can relabel.
Only predictions with top1_confidence < 0.7 can be relabeled.
Relabel must write audit log.
Relabel must invalidate affected caches.
```

Flow:

```text
route
↓
PredictionService.relabel_prediction()
↓
PredictionRepository.get_by_id()
↓
validate confidence < 0.7
↓
PredictionRepository.update_corrected_label()
↓
Audit service/repository writes event
↓
CacheService invalidates:
  - recent predictions
  - batch list
  - specific batch detail
↓
return updated prediction
```

---

## Service Files

## 1. app/services/batch_service.py

Responsibilities:

- Business logic for reading/listing batches.
- Use cache for GET /batches and GET /batches/{id}.
- Call BatchRepository.
- check permissions via permission service.
- Return domain/API schemas.
- No raw SQL.

Recommended methods:

```python
class BatchService:
    async def list_batches(
        self,
        *,
        status: BatchStatus | None,
        limit: int,
        offset: int,
        current_user: CurrentUser,
    ) -> PaginatedBatchSummary: ...

    async def get_batch_detail(
        self,
        *,
        batch_id: UUID,
        current_user: CurrentUser,
    ) -> BatchDetail: ...

    async def mark_batch_state_changed(
        self,
        *,
        batch_id: UUID,
        new_status: BatchStatus,
        actor: str | None,
        request_id: str,
    ) -> None: ...
```

Notes:

- `mark_batch_state_changed` may be called by workers later.
- The worker owner may need this service when updating batch status.
- Cache invalidation for batch status changes belongs here or in a helper called by this service.

---

## 2. app/services/prediction_service.py

Responsibilities:

- Business logic for recent predictions.
- Business logic for relabel.
- Enforce relabel confidence rule.
- Write audit log through audit service/repository.
- Invalidate caches after write.

Recommended methods:

```python
class PredictionService:
    async def get_recent_predictions(
        self,
        *,
        limit: int,
        only_needs_review: bool,
        current_user: CurrentUser,
    ) -> RecentPredictionsResponse: ...

    async def relabel_prediction(
        self,
        *,
        prediction_id: UUID,
        corrected_label: DocumentClass,
        current_user: CurrentUser,
        request_id: str,
    ) -> PredictionRead: ...

    async def create_prediction_from_worker(
        self,
        *,
        document_id: UUID,
        prediction_result: PredictionResult,
        request_id: str,
    ) -> PredictionRead: ...
```

Important:

`create_prediction_from_worker` is for integration with the inference worker.

It should:

- Save prediction.
- Set `needs_review = top1_confidence < 0.7`.
- Update document status if needed.
- Invalidate recent predictions and batch detail cache.

---

## 3. app/services/cache_service.py

Responsibilities:

- Build cache keys.
- Get cached values.
- Set cached values.
- Invalidate affected keys after writes.
- Hide Redis/fastapi-cache2 details from services.

Recommended methods:

```python
class CacheService:
    async def get_json(self, key: str) -> dict | list | None: ...

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def invalidate_batch_list(self) -> None: ...

    async def invalidate_batch_detail(self, batch_id: UUID) -> None: ...

    async def invalidate_recent_predictions(self) -> None: ...

    async def invalidate_after_prediction_write(self, batch_id: UUID) -> None: ...

    async def invalidate_after_relabel(self, batch_id: UUID) -> None: ...
```

Recommended cache keys:

```text
me:{user_id}
batches:list:{status}:{limit}:{offset}
batches:detail:{batch_id}
predictions:recent:{limit}:{only_needs_review}
```

Required cached endpoints from brief:

```text
GET /me
GET /batches
GET /batches/{bid}
GET /predictions/recent
```

Your part likely owns the last three.

---

## Repository Files

## 1. app/repositories/batch_repository.py

Responsibilities:

- Query batch list.
- Query one batch.
- Count documents/predictions per batch.
- Update batch status.

Recommended methods:

```python
class BatchRepository:
    async def list_batches(
        self,
        *,
        status: BatchStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[BatchSummary], int]: ...

    async def get_batch_detail(
        self,
        *,
        batch_id: UUID,
    ) -> BatchDetail | None: ...

    async def update_status(
        self,
        *,
        batch_id: UUID,
        status: BatchStatus,
    ) -> None: ...

    async def get_batch_id_for_document(
        self,
        *,
        document_id: UUID,
    ) -> UUID | None: ...
```

---

## 2. app/repositories/document_repository.py

Responsibilities:

- Fetch document metadata.
- Update document status.
- Attach overlay blob key.

Recommended methods:

```python
class DocumentRepository:
    async def get_by_id(self, document_id: UUID) -> DocumentRead | None: ...

    async def update_status(
        self,
        *,
        document_id: UUID,
        status: DocumentStatus,
        error_message: str | None = None,
    ) -> None: ...

    async def set_overlay_key(
        self,
        *,
        document_id: UUID,
        overlay_blob_key: str,
    ) -> None: ...
```

---

## 3. app/repositories/prediction_repository.py

Responsibilities:

- Fetch prediction.
- Create prediction.
- Fetch recent predictions.
- Relabel prediction.

Recommended methods:

```python
class PredictionRepository:
    async def get_by_id(self, prediction_id: UUID) -> PredictionRead | None: ...

    async def get_recent_predictions(
        self,
        *,
        limit: int,
        only_needs_review: bool,
    ) -> list[PredictionRead]: ...

    async def create_prediction(
        self,
        *,
        document_id: UUID,
        predicted_label: DocumentClass,
        top1_confidence: float,
        top5_labels: list[DocumentClass],
        top5_confidences: list[float],
        model_version: str,
        model_sha256: str,
        inference_ms: float,
        needs_review: bool,
    ) -> PredictionRead: ...

    async def update_corrected_label(
        self,
        *,
        prediction_id: UUID,
        corrected_label: DocumentClass,
        reviewed_by: UUID,
    ) -> PredictionRead: ...
```

---

## Domain Files You May Need

## app/domain/batch.py

Should include:

```python
BatchStatus
BatchSummary
BatchDetail
PaginatedBatchSummary
```

## app/domain/document.py

Should include:

```python
DocumentStatus
DocumentRead
DocumentWithPrediction
```

## app/domain/prediction.py

Should include:

```python
DocumentClass
TopKPrediction
PredictionRead
PredictionResult
RecentPredictionsResponse
RelabelRequest
```

## app/domain/pagination.py

Should include:

```python
PaginationParams
PaginatedResponse
```

If another teammate owns domain/contracts, coordinate with them and reuse their types.

Do NOT create duplicate enums in many files.

---

## Caching Rules

Cache reads:

- GET /batches
- GET /batches/{batch_id}
- GET /predictions/recent

Invalidate on writes:

### When new prediction is created

Invalidate:

```text
predictions:recent:*
batches:list:*
batches:detail:{batch_id}
```

### When prediction is relabeled

Invalidate:

```text
predictions:recent:*
batches:list:*
batches:detail:{batch_id}
```

### When batch status changes

Invalidate:

```text
batches:list:*
batches:detail:{batch_id}
```

Important:
Invalidation lives in service layer, not route or repository.

---

## Permission Logic You Must Respect

Roles:

```text
admin
reviewer
auditor
```

Rules:

```text
admin: can view batches, predictions, audit logs, toggle roles
reviewer: can view batches and relabel low-confidence predictions
auditor: read-only batches and audit logs
```

For your routes:

```text
GET /batches            admin/reviewer/auditor
GET /batches/{id}       admin/reviewer/auditor
GET /predictions/recent admin/reviewer/auditor or reviewer/admin depending team decision
PATCH /predictions/{id}/relabel reviewer/admin only
```

Relabel rule:

```text
top1_confidence < 0.7
```

Never allow relabel if confidence is >= 0.7.

---

## Errors To Handle

Use clean service exceptions, then map to HTTP in route or exception handler.

Recommended custom exceptions:

```python
NotFoundError
ForbiddenError
ValidationConflictError
BusinessRuleViolationError
```

Examples:

```text
batch not found → 404
prediction not found → 404
user cannot relabel → 403
prediction confidence too high → 409 or 400
invalid corrected label → 422
```

Do not expose stack traces.

---

## Integration Points With Other Members

## With Auth/Permission Owner

You need:

```python
get_current_user()
require_permission()
```

or a service like:

```python
PermissionService.ensure_can_view_batches(user)
PermissionService.ensure_can_relabel(user)
```

If not ready, create temporary stubs and mark TODO.

---

## With DB Owner

You need SQLAlchemy ORM models:

```text
Batch
Document
Prediction
AuditLog
User
```

You should not invent final DB columns alone.
Coordinate on fields.

---

## With Worker Owner

They need to call:

```python
PredictionService.create_prediction_from_worker()
BatchService.mark_batch_state_changed()
DocumentRepository.update_status()
```

Or you expose worker-safe service methods.

This avoids workers writing random SQL directly.

---

## With ML Owner

You consume:

```python
PredictionResult
```

from classifier output.

Expected fields:

```text
predicted_label
top1_confidence
top5 labels/confidences
model_version
model_sha256
inference_ms
```

---

## Minimal Implementation Order For Your Part

1. Define/reuse domain schemas.
2. Implement repositories with async SQLAlchemy.
3. Implement cache service.
4. Implement batch service.
5. Implement prediction service.
6. Implement batch routes.
7. Implement prediction routes.
8. Add tests using fake repositories/services.
9. Integrate with real DB.
10. Integrate with worker-created predictions.

---

## Recommended Codex Prompt For Your Part

Use this prompt:

```text
You are working inside a Week 6 AI Engineering project: Document Classifier as an Authenticated Service.

I am Member C. My ownership is:
Core API layer, repositories, services, caching, batch routes, and prediction routes.

Build my part with clean layered architecture.

Project architecture:
- FastAPI routes must be thin.
- Routes call services only.
- Services own business logic, cache invalidation, and transaction boundaries.
- Services call repositories for database access.
- Services call infra/cache adapters for Redis caching.
- Repositories own SQL only.
- Repositories must not raise HTTPException.
- Repositories must not invalidate cache.
- Do not run inference in API.
- API only reads/manages results produced by workers.

Implement or update these files:
- app/api/routers/batches.py
- app/api/routers/predictions.py
- app/services/batch_service.py
- app/services/prediction_service.py
- app/services/cache_service.py
- app/repositories/batch_repository.py
- app/repositories/document_repository.py
- app/repositories/prediction_repository.py
- app/domain/batch.py
- app/domain/document.py
- app/domain/prediction.py
- app/domain/pagination.py

Expected routes:
- GET /batches
- GET /batches/{batch_id}
- GET /predictions/recent
- PATCH /predictions/{prediction_id}/relabel

Business rules:
- GET batch routes are allowed for admin/reviewer/auditor.
- Relabel is allowed only for reviewer/admin.
- Relabel is allowed only when top1_confidence < 0.7.
- Relabel writes an audit event.
- Relabel invalidates caches.
- Prediction creation from worker sets needs_review = top1_confidence < 0.7.
- Cache these reads:
  - GET /batches
  - GET /batches/{batch_id}
  - GET /predictions/recent
- Invalidate caches after:
  - prediction created
  - prediction relabeled
  - batch status changed

Use Python 3.11, Pydantic v2, async SQLAlchemy 2.x style, type hints, clean docstrings, and junior-readable code.

Do not import SQLAlchemy models in routes.
Do not import FastAPI in repositories.
Do not import Redis directly in repositories.
Use dependency injection-friendly constructors for services and repositories.

If auth/permission/audit dependencies do not exist yet, create small interfaces/stubs with clear TODO comments instead of hardcoding messy logic.

Also add minimal tests for:
- list batches calls repository and cache
- get batch detail returns cached value when available
- relabel rejects confidence >= 0.7
- relabel invalidates caches
- recent predictions route returns service response
```

---

## Success Checklist

Your part is successful if:

- routes are thin
- services contain business logic
- repositories contain SQL only
- cache invalidation is not in routers/repos
- relabel rule is enforced
- batch detail returns documents + predictions
- worker can reuse service methods
- tests prove core behavior
- your code can be explained live on Friday

---

## One-Sentence Explanation For Presentation

My part owns the API core for reading and reviewing classification results: routes receive authenticated requests, services enforce business rules and caching, repositories isolate database access, and prediction relabels safely update state with audit logging and cache invalidation.
