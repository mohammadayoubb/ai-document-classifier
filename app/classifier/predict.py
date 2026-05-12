"""Single-image prediction helper for the document classifier.

This module is responsible for:
- loading images from path, bytes, or PIL
- applying the same preprocessing used during training
- running classifier inference
- returning top-1 label, confidence, top-5 labels/scores, and low-confidence flag

No environment variables are read here.
Settings are injected or loaded through get_settings().
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from PIL import Image, ImageFile, UnidentifiedImageError
from torchvision import transforms

from app.config import Settings, get_settings
from app.classifier.model import ClassifierArtifactError, load_and_verify_classifier

ImageFile.LOAD_TRUNCATED_IMAGES = True


class ClassifierPredictionError(RuntimeError):
    """Raised when an image cannot be loaded or classified."""


@dataclass(frozen=True)
class TopPrediction:
    """One prediction item."""

    label: str
    confidence: float
    class_index: int


@dataclass(frozen=True)
class ClassifierPrediction:
    """Classifier prediction result."""

    label: str
    confidence: float
    class_index: int
    top5: list[TopPrediction]
    low_confidence: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert prediction result to a JSON-friendly dictionary."""
        return {
            "label": self.label,
            "confidence": self.confidence,
            "class_index": self.class_index,
            "top5": [asdict(item) for item in self.top5],
            "low_confidence": self.low_confidence,
        }


def build_eval_transform(input_size: int = 224) -> transforms.Compose:
    """Build the exact evaluation transform used in the training notebook.

    Args:
        input_size: Final image crop size.

    Returns:
        Torchvision transform pipeline.
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


def load_pil_image_from_path(image_path: str | Path) -> Image.Image:
    """Load an image from a file path.

    Args:
        image_path: Path to image file.

    Returns:
        Loaded RGB PIL image.

    Raises:
        ClassifierPredictionError: If the image cannot be opened.
    """
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


def load_pil_image_from_bytes(image_bytes: bytes) -> Image.Image:
    """Load an image from raw bytes.

    Args:
        image_bytes: Raw image bytes.

    Returns:
        Loaded RGB PIL image.

    Raises:
        ClassifierPredictionError: If bytes cannot be decoded as an image.
    """
    if not image_bytes:
        raise ClassifierPredictionError("Image bytes are empty.")

    try:
        image = Image.open(BytesIO(image_bytes))
        image.load()
        return image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ClassifierPredictionError("Could not decode image bytes.") from error


def validate_labels(labels: list[str]) -> None:
    """Validate classifier labels from settings.

    Args:
        labels: Class labels from Settings.

    Raises:
        ClassifierPredictionError: If labels are missing or invalid.
    """
    if not labels:
        raise ClassifierPredictionError("settings.classifier_labels must not be empty.")

    if len(set(labels)) != len(labels):
        raise ClassifierPredictionError("settings.classifier_labels contains duplicate labels.")


class ClassifierPredictor:
    """Reusable classifier predictor.

    The API/worker should create this once at startup and reuse it.
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
        self.transform = build_eval_transform(input_size=224)

        self.model = model.to(self.device)
        self.model.eval()

        for parameter in self.model.parameters():
            parameter.requires_grad = False

    @torch.inference_mode()
    def predict_pil_image(self, image: Image.Image) -> ClassifierPrediction:
        """Classify one PIL image.

        Args:
            image: PIL image.

        Returns:
            Prediction result.

        Raises:
            ClassifierPredictionError: If inference fails.
        """
        try:
            image = image.convert("RGB")
            tensor = self.transform(image).unsqueeze(0).to(self.device)

            logits = self.model(tensor)
            probabilities = torch.softmax(logits, dim=1)

            top_k = min(5, len(self.labels))
            top_scores, top_indices = torch.topk(probabilities, k=top_k, dim=1)

            top_scores_list = top_scores[0].detach().cpu().tolist()
            top_indices_list = top_indices[0].detach().cpu().tolist()

            top_predictions = [
                TopPrediction(
                    label=self.labels[class_index],
                    confidence=float(score),
                    class_index=int(class_index),
                )
                for class_index, score in zip(top_indices_list, top_scores_list, strict=True)
            ]

            best = top_predictions[0]

            return ClassifierPrediction(
                label=best.label,
                confidence=best.confidence,
                class_index=best.class_index,
                top5=top_predictions,
                low_confidence=best.confidence < self.settings.low_confidence_threshold,
            )

        except IndexError as error:
            raise ClassifierPredictionError(
                "Model output class index does not match settings.classifier_labels."
            ) from error
        except RuntimeError as error:
            raise ClassifierPredictionError("Classifier inference failed.") from error

    def predict_path(self, image_path: str | Path) -> ClassifierPrediction:
        """Classify one image from a file path."""
        image = load_pil_image_from_path(image_path)
        return self.predict_pil_image(image)

    def predict_bytes(self, image_bytes: bytes) -> ClassifierPrediction:
        """Classify one image from raw bytes."""
        image = load_pil_image_from_bytes(image_bytes)
        return self.predict_pil_image(image)


def create_classifier_predictor(
    settings: Settings | None = None,
    *,
    device: torch.device | str = "cpu",
) -> ClassifierPredictor:
    """Create a verified classifier predictor.

    This loads and verifies classifier.pt using model.py.

    Args:
        settings: Optional application settings. If omitted, get_settings() is used.
        device: Inference device. Default is CPU.

    Returns:
        Ready-to-use predictor.

    Raises:
        ClassifierArtifactError: If model artifacts are invalid.
        ClassifierPredictionError: If predictor setup fails.
    """
    resolved_settings = settings or get_settings()

    try:
        model = load_and_verify_classifier(resolved_settings)
    except ClassifierArtifactError:
        raise
    except Exception as error:
        raise ClassifierPredictionError("Could not create classifier predictor.") from error

    return ClassifierPredictor(
        model=model,
        settings=resolved_settings,
        device=device,
    )


def predict_image_path(
    image_path: str | Path,
    settings: Settings | None = None,
    *,
    device: torch.device | str = "cpu",
) -> dict[str, Any]:
    """Convenience function for classifying one image path.

    This loads the model each time, so it is useful for scripts/tests.
    In the API/worker, prefer creating ClassifierPredictor once and reusing it.
    """
    predictor = create_classifier_predictor(settings=settings, device=device)
    prediction = predictor.predict_path(image_path)
    return prediction.to_dict()


def predict_image_bytes(
    image_bytes: bytes,
    settings: Settings | None = None,
    *,
    device: torch.device | str = "cpu",
) -> dict[str, Any]:
    """Convenience function for classifying one image from bytes.

    This loads the model each time, so it is useful for small scripts/tests.
    In the API/worker, prefer creating ClassifierPredictor once and reusing it.
    """
    predictor = create_classifier_predictor(settings=settings, device=device)
    prediction = predictor.predict_bytes(image_bytes)
    return prediction.to_dict()