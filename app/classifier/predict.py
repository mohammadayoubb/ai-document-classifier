"""Single-image inference function.

This module is synchronous — it is called from the RQ worker (a thread),
not from the async FastAPI event loop.
"""

from dataclasses import dataclass

import structlog
import torch

log = structlog.get_logger()


@dataclass
class PredictionResult:
    """Result of running inference on one image.

    Attributes:
        label: Top-1 predicted document class name.
        confidence: Top-1 confidence score in [0.0, 1.0].
        top5_labels: Top-5 class names ordered by confidence descending.
        top5_scores: Corresponding top-5 confidence scores.
    """

    label: str
    confidence: float
    top5_labels: list[str]
    top5_scores: list[float]


def classify_image(
    model: torch.nn.Module,
    image_bytes: bytes,
    labels: list[str],
) -> PredictionResult:
    """Run inference on raw image bytes and return top-1 and top-5 results.

    Designed to run in the RQ worker thread — synchronous, no async I/O.
    For use from an async context, wrap with asyncio.to_thread().

    p95 latency target: < 1.0s on CPU with ConvNeXt Tiny.

    Args:
        model: Loaded ConvNeXt model in eval mode.
        image_bytes: Raw TIFF or PNG bytes from MinIO.
        labels: Ordered list of 16 RVL-CDIP class names.

    Returns:
        PredictionResult with top-1 label, confidence, and top-5.

    Raises:
        ValueError: If image_bytes cannot be decoded as a valid image.
    """
    # TODO: Phase 7 — implement preprocessing (grayscale→RGB, resize 224×224,
    #   normalize with ImageNet mean/std) and inference pass
    ...  # type: ignore[return-value]
