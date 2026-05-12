# you should read all .md files under ai-document-classifier, they are the main context .
### Use this file as a second reference after all other .md files such as CLAUDE.md, PROJECT_PLAN.md ..., so what conflict among them, do not use this file, use them instead. this is just as a complementary for anything missing there.

### My part is Member C, so we should keep the cope of working to only the folders for this part, so that we do not introduce any git conflict

## Week 6 — Document Classifier as an Authenticated Service

## Core Idea

Build an internal document classification platform.

Documents enter through SFTP.
Workers process them asynchronously.
Predictions are stored in Postgres.
Authenticated users browse/review predictions through FastAPI.

The project is NOT just ML.
Main focus:
- architecture
- clean layering
- async/background systems
- security
- infra integration
- collaboration

---

## Main Technologies

- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Redis
- RQ
- MinIO
- atmoz/sftp
- Vault
- Casbin
- fastapi-users
- PyTorch + torchvision
- Docker Compose

---

## Main System Flows

### Flow 1 — User/API Flow

Used by:
- admin
- reviewer
- auditor

Flow:

User
↓ HTTP/JWT
API Routes
↓
Services
↓
Repositories + Infra
↓
Postgres / Redis / Vault / Casbin / MinIO

Purpose:
- login
- view batches
- view predictions
- relabel predictions
- toggle roles
- view audit logs

---

### Flow 2 — Document Processing Flow

Triggered by:
new TIFF file dropped into SFTP.

Flow:

External uploader
↓ SFTP upload
SFTP Server
↓ polling
sftp-ingest worker
↓
MinIO + Postgres + Redis/RQ
↓
inference worker
↓
classifier
↓
Postgres + MinIO
↓
API exposes results

Purpose:
- classify documents asynchronously

IMPORTANT:
Users do NOT upload files through API.
Classification starts from SFTP.

---

## Main Components

### 1. API

Purpose:
- authentication
- authorization
- exposing endpoints
- viewing predictions/batches
- role management

Does NOT:
- run inference
- directly use SQLAlchemy
- directly use MinIO/Redis

Main routes:
- POST /auth/register
- POST /auth/jwt/login
- GET /me
- GET /batches
- GET /batches/{id}
- GET /predictions/recent
- PATCH /predictions/{id}/relabel
- POST /users/{id}/role
- GET /audit-log

---

### 2. Services

Purpose:
business logic.

Examples:
- permission checks
- relabel rules
- cache invalidation
- audit logging
- orchestration

Pattern:

routes
↓
services
↓
repositories + infra

Services use:
- repositories for DB
- infra adapters for external systems

---

### 3. Repositories

Purpose:
SQL/database operations only.

Examples:
- create batch
- fetch prediction
- update document status

Repositories should NOT:
- contain business logic
- invalidate cache
- call MinIO
- raise HTTPException

Pattern:

service
↓
repository
↓
Postgres

---

### 4. Infra

Purpose:
adapters for external systems.

Examples:
- SFTP adapter
- MinIO adapter
- Redis adapter
- RQ adapter
- Vault adapter
- Casbin adapter

Infra isolates low-level integrations.

Without infra:
services become messy and tightly coupled.

Correct pattern:

services
↓
infra adapters
↓
external systems

---

### 5. SFTP

Purpose:
entry point for document files.

Acts like:
secure upload folder.

Example:
scp invoice_001.tiff user@localhost:/upload

SFTP only stores incoming files.

It does NOT:
- classify
- call API
- touch DB

---

### 6. sftp-ingest Worker

Purpose:
watch SFTP folder and create jobs.

Runs polling loop:
- list files every few seconds
- detect new TIFFs
- validate files
- upload originals to MinIO
- create DB rows
- enqueue jobs

Communicates with:
- SFTP
- MinIO
- Postgres
- Redis/RQ

---

### 7. MinIO

Purpose:
blob/object storage.

Stores:
- original TIFFs
- overlay PNGs

Postgres stores:
metadata only.

Example:
blob_key = originals/batch123/invoice_001.tiff

MinIO stores actual binary file.

---

### 8. Redis

Purpose:
in-memory data store.

Used for:
- queue storage
- cache storage

Redis itself is NOT the worker system.

---

### 9. RQ

Purpose:
Python queue system built on Redis.

Pattern:

sftp-ingest
↓ enqueue
RQ
↓ stores jobs in Redis
worker
↓ consumes jobs

Redis = storage.
RQ = queue framework.

---

### 10. Inference Worker

Purpose:
consume jobs and run classifier.

Flow:

receive ClassificationJob
↓
download TIFF from MinIO
↓
run classifier
↓
save prediction in Postgres
↓
upload overlay PNG to MinIO
↓
invalidate cache

Does NOT expose HTTP endpoints.

---

### 11. Classifier Module

Purpose:
encapsulate ML inference.

Responsibilities:
- load classifier.pt
- validate SHA-256
- preprocess image
- run ConvNeXt
- return PredictionResult

Expose simple interface:

classifier.predict(image_bytes)

Worker should NOT know ML internals.

---

### 12. Vault

Purpose:
centralized secret management.

Stores:
- JWT secret
- DB password
- MinIO credentials
- SFTP credentials
- Redis credentials

Without Vault:
everything lives in .env.

Vault adds:
- security
- centralized secrets
- production-style architecture
- secret rotation capability

API/worker should refuse startup if Vault unavailable.

---

### 13. Casbin

Purpose:
role-based access control.

Roles:
- admin
- reviewer
- auditor

Examples:
- admin can toggle roles
- reviewer can relabel low-confidence predictions
- auditor is read-only

---

## Batches

Batch = group of uploaded documents.

Example:

batch_001/
  invoice_001.tiff
  memo_002.tiff

Purpose:
- grouping documents
- tracking processing
- showing progress
- organizing predictions

Relationship:

Batch
 ├── Document
 │     └── Prediction
 └── Document
       └── Prediction

---

## Main Database Tables

### users
auth users.

### batches
group of uploaded documents.

### documents
individual files.

### predictions
model outputs.

### audit_logs
tracks:
- role changes
- relabels
- batch state changes

---

## Layered Architecture

Correct dependency direction:

routes
↓
services
↓              ↓
repositories   infra adapters
↓              ↓
Postgres       Redis / MinIO / SFTP / Vault / Casbin

Golden rules:
- routes never touch DB directly
- routes never touch MinIO directly
- repositories only handle SQL
- services own business logic
- infra owns external integrations

---

## Repo Structure

app/
├── api/
├── services/
├── repositories/
├── domain/
├── infra/
├── db/
├── classifier/
├── workers/
└── core/

---

## Docker Architecture

Use:
- ONE repo
- ONE pyproject.toml
- ONE Dockerfile
- ONE shared image
- MULTIPLE containers

Containers:
- api
- worker
- sftp-ingest
- migrate
- db
- redis
- minio
- sftp
- vault

api/worker/sftp-ingest/migrate use same image but different commands.

---

## Compose Logic

api:
runs FastAPI.

worker:
runs inference worker.

sftp-ingest:
runs polling worker.

migrate:
runs alembic upgrade head.

---

## Contracts

Purpose:
shared language between components.

Examples:
- ClassificationJob
- PredictionResult
- BatchStatus
- DocumentStatus

Used by:
- sftp-ingest creates jobs
- worker parses jobs
- classifier returns predictions
- API returns schemas
- tests validate structures

Important:
contracts must NOT import FastAPI/SQLAlchemy/Redis.

Contracts should be pure Pydantic domain models.


## Dummy Inference Strategy

Before real ML:

return:
{
  "predicted_label": "invoice",
  "top1_confidence": 0.91
}

Purpose:
- unblock backend
- test architecture early
- reduce integration risk

---

## Team Split

### Person 1 — ML
- ConvNeXt training
- classifier.pt
- model_card.json
- golden set
- inference module

### Person 2 — API/Auth
- FastAPI routes
- fastapi-users
- Casbin
- audit routes
- role management

### Person 3 — DB/Services
- SQLAlchemy
- Alembic
- repositories
- services
- cache
- Vault

### Person 4 — Workers/Infra
- sftp-ingest
- RQ worker
- MinIO
- SFTP
- CI
- compose integration

---

## Important Architecture Notes

- API never runs inference.
- Workers should use services too.
- MinIO stores files, not Postgres.
- Redis stores queue/cache data.
- RQ manages jobs on Redis.
- Vault manages secrets.
- Services orchestrate everything.
- Repositories only talk to DB.
- Infra only talks to external systems.

---

## Final Mental Model

SFTP = document entry door
sftp-ingest = detects/uploads/enqueues
Redis/RQ = job pipeline
worker = classifier executor
MinIO = file storage
Postgres = metadata storage
FastAPI = authenticated access layer
Vault = secret manager
Casbin = permission engine
services = business brain
contracts = shared language