"""Prediction helpers for the document classifier.

This module exposes the teammate-compatible API:

    classify_image(model, image_bytes, labels) -> PredictionResult

It also provides optional reusable predictor helpers for API/worker code.

No environment variables are read here.
Settings are injected or loaded through get_settings().
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import logging

import torch
import torch.nn as nn
from PIL import Image, ImageFile, UnidentifiedImageError
from torchvision import transforms

from app.config import Settings, get_settings
from app.classifier.model import ClassifierArtifactError, load_and_verify

try:
    import structlog

    log = structlog.get_logger()
except ImportError:
    log = logging.getLogger(__name__)


ImageFile.LOAD_TRUNCATED_IMAGES = True


class ClassifierPredictionError(RuntimeError):
    """Raised when an image cannot be loaded or classified."""


@dataclass(frozen=True)
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

    def to_dict(self) -> dict[str, Any]:
        """Convert prediction result to a JSON-friendly dictionary."""
        return asdict(self)


def build_eval_transform(input_size: int = 224) -> transforms.Compose:
    """Build the evaluation transform used during training.

    Training notebook eval transform:
    - convert grayscale/TIFF document to RGB
    - resize shorter side to 256
    - center crop to 224x224
    - convert to tensor
    - normalize with ImageNet mean/std
    """
    imagenet_mean = [0.485, 0.456, 0.406]
    imagenet_std = [0.229, 0.224, 0.225]

    return transforms.Compose(
        [
            transforms.Lambda(lambda image: image.convert("RGB")),
            transforms.Resize(256),
            transforms.CenterCrop(input_size),
            transforms.ToTensor(),
            transforms.Normalize(mean=imagenet_mean, std=imagenet_std),
        ]
    )


def validate_labels(labels: list[str]) -> None:
    """Validate ordered classifier labels."""
    if not labels:
        raise ValueError("labels must not be empty.")

    if len(set(labels)) != len(labels):
        raise ValueError("labels contains duplicate class names.")


def load_pil_image_from_bytes(image_bytes: bytes) -> Image.Image:
    """Decode raw image bytes into an RGB PIL image.

    Args:
        image_bytes: Raw TIFF/PNG/JPEG/etc. bytes.

    Returns:
        RGB PIL image.

    Raises:
        ValueError: If the bytes cannot be decoded as an image.
    """
    if not image_bytes:
        raise ValueError("image_bytes cannot be empty.")

    try:
        image = Image.open(BytesIO(image_bytes))
        image.load()
        return image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValueError("image_bytes could not be decoded as a valid image.") from error


def load_pil_image_from_path(image_path: str | Path) -> Image.Image:
    """Load an image from a local file path."""
    path = Path(image_path)

    if not path.exists():
        raise ClassifierPredictionError(f"Image file not found: {path}")

    if not path.is_file():
        raise ClassifierPredictionError(f"Image path is not a file: {path}")

    try:
        image = Image.open(path)
        image.load()
        return image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ClassifierPredictionError(f"Could not load image file: {path}") from error


def get_model_device(model: nn.Module) -> torch.device:
    """Return the device where the model currently lives."""
    try:
        return next(model.parameters()).device
    except StopIteration:
        return torch.device("cpu")


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
        image_bytes: Raw TIFF/PNG/JPEG bytes from MinIO.
        labels: Ordered list of 16 RVL-CDIP class names.

    Returns:
        PredictionResult with top-1 label, confidence, and top-5.

    Raises:
        ValueError: If image_bytes cannot be decoded or labels are invalid.
        ClassifierPredictionError: If inference fails.
    """
    validate_labels(labels)

    image = load_pil_image_from_bytes(image_bytes)
    transform = build_eval_transform(input_size=224)

    model.eval()
    device = get_model_device(model)

    try:
        tensor = transform(image).unsqueeze(0).to(device)

        with torch.inference_mode():
            logits = model(tensor)
            probabilities = torch.softmax(logits, dim=1)

            top_k = min(5, len(labels))
            top_scores, top_indices = torch.topk(probabilities, k=top_k, dim=1)

        top_indices_list = top_indices[0].detach().cpu().tolist()
        top_scores_list = top_scores[0].detach().cpu().tolist()

        top5_labels = []
        top5_scores = []

        for class_index, score in zip(top_indices_list, top_scores_list, strict=True):
            if class_index >= len(labels):
                raise ClassifierPredictionError(
                    "Model output class index does not match provided labels."
                )

            top5_labels.append(labels[int(class_index)])
            top5_scores.append(float(score))

        result = PredictionResult(
            label=top5_labels[0],
            confidence=top5_scores[0],
            top5_labels=top5_labels,
            top5_scores=top5_scores,
        )

        log.info(
            "classifier.predicted",
            label=result.label,
            confidence=result.confidence,
        )

        return result

    except ClassifierPredictionError:
        raise
    except RuntimeError as error:
        raise ClassifierPredictionError("Classifier inference failed.") from error


class ClassifierPredictor:
    """Reusable classifier predictor.

    The API/worker can create this once at startup and reuse it.
    """

    def __init__(
        self,
        *,
        model: nn.Module,
        settings: Settings,
        device: torch.device | str = "cpu",
    ) -> None:
        validate_labels(settings.classifier_labels)

        self.settings = settings
        self.labels = settings.classifier_labels
        self.device = torch.device(device)

        self.model = model.to(self.device)
        self.model.eval()

        for parameter in self.model.parameters():
            parameter.requires_grad = False

    def predict_bytes(self, image_bytes: bytes) -> PredictionResult:
        """Classify one image from raw bytes."""
        return classify_image(
            model=self.model,
            image_bytes=image_bytes,
            labels=self.labels,
        )

    def predict_path(self, image_path: str | Path) -> PredictionResult:
        """Classify one image from a local file path."""
        path = Path(image_path)

        try:
            image_bytes = path.read_bytes()
        except OSError as error:
            raise ClassifierPredictionError(f"Could not read image file: {path}") from error

        return self.predict_bytes(image_bytes)


def create_classifier_predictor(
    settings: Settings | None = None,
    *,
    device: torch.device | str = "cpu",
) -> ClassifierPredictor:
    """Create a verified reusable classifier predictor.

    Uses app.classifier.model.load_and_verify(settings), which is the
    teammate-compatible verified model loader.
    """
    resolved_settings = settings or get_settings()

    try:
        model = load_and_verify(resolved_settings)
    except ClassifierArtifactError:
        raise
    except Exception as error:
        raise ClassifierPredictionError("Could not create classifier predictor.") from error

    return ClassifierPredictor(
        model=model,
        settings=resolved_settings,
        device=device,
    )


def predict_image_bytes(
    image_bytes: bytes,
    settings: Settings | None = None,
    *,
    device: torch.device | str = "cpu",
) -> dict[str, Any]:
    """Convenience function for classifying one image from bytes.

    This loads the model each time, so it is useful for scripts/tests.
    In API/worker code, prefer creating ClassifierPredictor once.
    """
    predictor = create_classifier_predictor(settings=settings, device=device)
    return predictor.predict_bytes(image_bytes).to_dict()


def predict_image_path(
    image_path: str | Path,
    settings: Settings | None = None,
    *,
    device: torch.device | str = "cpu",
) -> dict[str, Any]:
    """Convenience function for classifying one image from a local path.

    This loads the model each time, so it is useful for scripts/tests.
    In API/worker code, prefer creating ClassifierPredictor once.
    """
    predictor = create_classifier_predictor(settings=settings, device=device)
    return predictor.predict_path(image_path).to_dict()