"""RQ inference worker — consumes jobs and runs the ConvNeXt classifier.

Start via:
    rq worker --url redis://redis:6379

The RQ job function (run_inference_job) is synchronous because RQ executes
jobs in threads. The async implementation (_async_run_inference) is called
via asyncio.run() which creates a fresh event loop — safe because RQ workers
are separate processes with no pre-existing loop.

Per-job lifecycle:
  1. Download image bytes from MinIO
  2. Run classify_image() (CPU inference)
  3. Generate annotated overlay PNG (Pillow)
  4. Upload overlay PNG to MinIO 'overlays' bucket
  5. Create Prediction row in DB (label, confidence, top5, overlay_key)
  6. Update Batch status to 'completed' (or 'failed' on error)
  7. Invalidate affected caches via service layer
  8. Log structured result including request_id for correlation with ingest logs
"""

import asyncio
import io
import json

import structlog
import torch
from PIL import Image, ImageDraw

from app.classifier.model import load_and_verify
from app.classifier.predict import PredictionResult, classify_image
from app.config import get_settings
from app.db.models import BatchStatus
from app.db.session import SessionLocal
from app.infra.blob import BlobStorage
from app.infra.cache import CacheAdapter
from app.infra.logging_setup import configure_logging
from app.infra.vault import VaultClient
from app.repositories.batch_repo import BatchRepository
from app.repositories.prediction_repo import PredictionRepository

log = structlog.get_logger()

# Module-level model cache — loaded once per RQ worker process
_model: torch.nn.Module | None = None


def _get_model() -> torch.nn.Module:
    """Return the cached classifier, loading it on first call."""
    global _model
    if _model is None:
        configure_logging()
        _model = load_and_verify(get_settings())
        log.info("inference.model.loaded")
    return _model


def _generate_overlay(image_bytes: bytes, label: str, confidence: float) -> bytes:
    """Draw predicted label and confidence bar onto the document image.

    Args:
        image_bytes: Raw bytes of the source document (TIFF or PNG).
        label: Top-1 predicted class label.
        confidence: Top-1 confidence score in [0.0, 1.0].

    Returns:
        PNG bytes of the annotated overlay image.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)

    banner_h = max(30, img.height // 20)

    # Black header banner with white label text
    draw.rectangle([0, 0, img.width, banner_h], fill=(0, 0, 0))
    draw.text((8, banner_h // 4), f"{label}  {confidence:.1%}", fill=(255, 255, 255))

    # Confidence bar at image bottom — green fill proportional to confidence
    bar_h = max(10, img.height // 40)
    bar_w = int(img.width * confidence)
    draw.rectangle([0, img.height - bar_h, img.width, img.height], fill=(180, 30, 30))
    draw.rectangle([0, img.height - bar_h, bar_w, img.height], fill=(30, 180, 30))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _async_run_inference(batch_id: int, filename: str, storage_key: str) -> None:
    """Async implementation of the full inference pipeline.

    Separated from the sync RQ entry point so we can use await throughout
    while keeping run_inference_job() synchronous as RQ requires.

    Args:
        batch_id: Primary key of the owning batch.
        filename: Original filename from the SFTP upload.
        storage_key: MinIO object key for the source document.
    """
    settings = get_settings()

    # Resolve MinIO secret from Vault each time the worker starts a job.
    # VaultClient is sync — fast enough that blocking is acceptable here.
    vault = VaultClient(addr=settings.vault_addr, token=settings.vault_token)
    minio_secret_key = vault.get_secret("app", "minio_secret_key")

    blob = BlobStorage(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=minio_secret_key,
    )
    cache = CacheAdapter()

    # 1. Download image from MinIO
    image_bytes = await blob.download("documents", storage_key)

    # 2. Classify — CPU-bound; run in thread to keep the event loop free
    model = _get_model()
    result: PredictionResult = await asyncio.to_thread(
        classify_image, model, image_bytes, settings.classifier_labels
    )
    log.info(
        "inference.classify.ok",
        batch_id=batch_id,
        label=result.label,
        confidence=result.confidence,
    )

    # 3. Generate annotated overlay PNG (CPU-bound)
    overlay_bytes = await asyncio.to_thread(
        _generate_overlay, image_bytes, result.label, result.confidence
    )

    # 4. Upload overlay to MinIO 'overlays' bucket
    base_name = storage_key.split("/")[-1]
    overlay_name = base_name.rsplit(".", 1)[0] + ".png"
    overlay_key = f"overlays/{overlay_name}"
    await blob.upload("overlays", overlay_key, overlay_bytes, "image/png")

    # 5–6. Persist prediction and update batch in a single transaction
    async with SessionLocal() as session:
        pred_repo = PredictionRepository(session)
        batch_repo = BatchRepository(session)

        pred = await pred_repo.create(
            batch_id=batch_id,
            filename=filename,
            storage_key=storage_key,
            predicted_label=result.label,
            confidence=result.confidence,
            top5_labels=json.dumps(result.top5_labels),
            top5_scores=json.dumps(result.top5_scores),
        )
        await pred_repo.update_overlay_key(pred.id, overlay_key)
        await batch_repo.update_status(batch_id, BatchStatus.completed)
        await session.commit()

    log.info(
        "inference.job.completed",
        batch_id=batch_id,
        prediction_id=pred.id,
        label=result.label,
        confidence=result.confidence,
        overlay_key=overlay_key,
    )

    # 7. Invalidate caches so API reads reflect the new prediction immediately
    await cache.invalidate_batches()
    await cache.invalidate_batch(batch_id)
    await cache.invalidate_recent_predictions()


async def _async_mark_failed(batch_id: int) -> None:
    """Update batch status to failed — called when the job encounters an error."""
    async with SessionLocal() as session:
        batch_repo = BatchRepository(session)
        await batch_repo.update_status(batch_id, BatchStatus.failed)
        await session.commit()

    cache = CacheAdapter()
    await cache.invalidate_batch(batch_id)
    await cache.invalidate_batches()


def run_inference_job(
    batch_id: int,
    filename: str,
    storage_key: str,
    request_id: str,
) -> None:
    """Classify one document and persist the results.

    This is the RQ job entry point — synchronous because RQ executes jobs
    in threads. Delegates to _async_run_inference via asyncio.run().

    p95 latency targets:
    - Inference step: < 1.0s (CPU, ConvNeXt Tiny)
    - End-to-end (SFTP drop → API response): < 10s

    Args:
        batch_id: Primary key of the owning batch.
        filename: Original filename from the SFTP upload.
        storage_key: MinIO object key for the source document to classify.
        request_id: Propagated from the ingest event for log correlation.
    """
    configure_logging()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    log.info(
        "inference.job.started",
        batch_id=batch_id,
        filename=filename,
        storage_key=storage_key,
    )

    try:
        asyncio.run(_async_run_inference(batch_id, filename, storage_key))
    except Exception as exc:
        log.exception("inference.job.failed", batch_id=batch_id, error=str(exc))
        asyncio.run(_async_mark_failed(batch_id))
        raise  # re-raise so RQ marks the job as failed
