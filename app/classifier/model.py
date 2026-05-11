"""ConvNeXt weight loading and startup integrity verification."""

import hashlib
import json
from pathlib import Path

import structlog
import torch
from torchvision import models

from app.config import Settings

log = structlog.get_logger()


def load_and_verify(settings: Settings) -> torch.nn.Module:
    """Load classifier weights and verify integrity and quality before startup.

    Three checks are performed — any failure raises RuntimeError and prevents
    the application from accepting requests:
    1. Weight file exists at settings.model_weights_path
    2. SHA-256 of the file matches model_card.json['sha256']
    3. model_card.json['test_top1'] >= settings.min_test_top1

    Args:
        settings: Application settings with paths and quality thresholds.

    Returns:
        A ConvNeXt-Tiny model loaded with the verified weights in eval mode.

    Raises:
        RuntimeError: On any verification failure.
    """
    weights_path = Path(settings.model_weights_path)
    card_path = Path(settings.model_card_path)

    if not weights_path.exists():
        raise RuntimeError(f"Classifier weights not found at {weights_path}")

    with card_path.open() as f:
        card: dict[str, object] = json.load(f)

    actual_sha256 = hashlib.sha256(weights_path.read_bytes()).hexdigest()
    expected_sha256 = str(card["sha256"])
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    test_top1 = float(str(card["test_top1"]))
    if test_top1 < settings.min_test_top1:
        raise RuntimeError(
            f"Model top-1 {test_top1:.3f} < required threshold {settings.min_test_top1}"
        )

    # weights_only=True avoids pickle RCE — mandatory for PyTorch >= 2.4
    model = models.convnext_tiny(weights=None, num_classes=16)
    state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state_dict)
    model.eval()

    log.info("classifier.loaded", sha256_prefix=actual_sha256[:12], test_top1=test_top1)
    return model
