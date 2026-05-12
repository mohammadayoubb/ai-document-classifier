"""Classifier model loading and artifact verification.

This module is responsible for:
- loading model_card.json
- verifying classifier.pt exists
- verifying classifier.pt SHA-256 matches the model card
- verifying test_top1 passes the configured threshold
- building the correct ConvNeXt architecture
- loading the trained state_dict
- returning a ready-to-use eval() model

No environment variables are read here.
All paths and thresholds come from Settings.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torchvision import models

# Change this import only if your config.py is in another folder.
# Example if your file is app/core/config.py:
# from app.core.config import Settings
from app.config import Settings


class ClassifierArtifactError(RuntimeError):
    """Raised when classifier artifacts are missing, invalid, or unsafe to use."""


def calculate_sha256(path: Path) -> str:
    """Calculate SHA-256 hash for a file.

    Args:
        path: File path to hash.

    Returns:
        Hex SHA-256 digest.
    """
    sha256 = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def load_model_card(model_card_path: str | Path) -> dict[str, Any]:
    """Load model_card.json.

    Args:
        model_card_path: Path to model_card.json.

    Returns:
        Parsed model card dictionary.

    Raises:
        ClassifierArtifactError: If the model card is missing or invalid.
    """
    path = Path(model_card_path)

    if not path.exists():
        raise ClassifierArtifactError(f"Model card not found: {path}")

    if not path.is_file():
        raise ClassifierArtifactError(f"Model card path is not a file: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            model_card = json.load(file)
    except json.JSONDecodeError as error:
        raise ClassifierArtifactError(
            f"Model card is not valid JSON: {path}"
        ) from error

    if not isinstance(model_card, dict):
        raise ClassifierArtifactError("Model card must be a JSON object.")

    return model_card


def get_expected_sha256(model_card: dict[str, Any]) -> str:
    """Read expected SHA-256 from model card.

    Supports both:
    - model_card["sha256"]
    - model_card["artifact"]["sha256"]
    """
    expected_sha256 = model_card.get("sha256")

    if expected_sha256 is None:
        artifact = model_card.get("artifact", {})
        if isinstance(artifact, dict):
            expected_sha256 = artifact.get("sha256")

    if not isinstance(expected_sha256, str) or not expected_sha256:
        raise ClassifierArtifactError(
            "Model card is missing SHA-256. Expected key 'sha256' or 'artifact.sha256'."
        )

    return expected_sha256


def get_test_top1(model_card: dict[str, Any]) -> float:
    """Read test top-1 accuracy from model card.

    Supports both:
    - model_card["test_top1"]
    - model_card["metrics"]["test_top1"]
    """
    value = model_card.get("test_top1")

    if value is None:
        metrics = model_card.get("metrics", {})
        if isinstance(metrics, dict):
            value = metrics.get("test_top1")

    if value is None:
        raise ClassifierArtifactError(
            "Model card is missing test_top1. Expected key 'test_top1' or 'metrics.test_top1'."
        )

    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ClassifierArtifactError("Model card test_top1 must be numeric.") from error


def get_backbone_name(model_card: dict[str, Any]) -> str:
    """Read backbone name from model card."""
    backbone = model_card.get("backbone")

    if backbone is None:
        model_section = model_card.get("model", {})
        if isinstance(model_section, dict):
            backbone = model_section.get("backbone")

    if not isinstance(backbone, str) or not backbone:
        raise ClassifierArtifactError(
            "Model card is missing backbone. Expected key 'backbone' or 'model.backbone'."
        )

    return backbone


def build_classifier_architecture(
    *,
    backbone: str,
    num_classes: int,
) -> nn.Module:
    """Build the model architecture used by the saved classifier state_dict.

    Args:
        backbone: Backbone name from model_card.json.
        num_classes: Number of classifier output classes.

    Returns:
        Untrained model architecture ready for state_dict loading.

    Raises:
        ClassifierArtifactError: If the backbone is unsupported.
    """
    normalized_backbone = backbone.strip().lower()

    if normalized_backbone == "convnext_tiny":
        model = models.convnext_tiny(weights=None)
    elif normalized_backbone == "convnext_small":
        model = models.convnext_small(weights=None)
    else:
        raise ClassifierArtifactError(
            f"Unsupported classifier backbone '{backbone}'. "
            "Supported backbones: convnext_tiny, convnext_small."
        )

    try:
        in_features = model.classifier[2].in_features
        model.classifier[2] = nn.Linear(in_features, num_classes)
    except (AttributeError, IndexError) as error:
        raise ClassifierArtifactError(
            f"Could not replace classifier head for backbone '{backbone}'."
        ) from error

    return model


def load_state_dict_safely(weights_path: Path) -> dict[str, torch.Tensor]:
    """Load a PyTorch state_dict from disk.

    The training notebook saved classifier.pt as a state_dict.
    This function also supports checkpoint dictionaries containing
    'model_state_dict' just in case.

    Args:
        weights_path: Path to classifier.pt.

    Returns:
        Model state_dict.

    Raises:
        ClassifierArtifactError: If the file cannot be loaded as a state_dict.
    """
    try:
        try:
            loaded_object = torch.load(
                weights_path,
                map_location="cpu",
                weights_only=True,
            )
        except TypeError:
            # Older PyTorch versions do not support weights_only.
            loaded_object = torch.load(weights_path, map_location="cpu")
    except Exception as error:
        raise ClassifierArtifactError(
            f"Could not load classifier weights from {weights_path}."
        ) from error

    if isinstance(loaded_object, dict) and "model_state_dict" in loaded_object:
        loaded_object = loaded_object["model_state_dict"]

    if not isinstance(loaded_object, dict):
        raise ClassifierArtifactError(
            "classifier.pt must contain a PyTorch state_dict or a checkpoint with model_state_dict."
        )

    return loaded_object


def verify_classifier_artifacts(settings: Settings) -> dict[str, Any]:
    """Verify model artifacts before loading the model.

    Args:
        settings: Application settings.

    Returns:
        Loaded model card.

    Raises:
        ClassifierArtifactError: If verification fails.
    """
    weights_path = Path(settings.model_weights_path)
    model_card_path = Path(settings.model_card_path)

    if not weights_path.exists():
        raise ClassifierArtifactError(f"Classifier weights not found: {weights_path}")

    if not weights_path.is_file():
        raise ClassifierArtifactError(f"Classifier weights path is not a file: {weights_path}")

    model_card = load_model_card(model_card_path)

    expected_sha256 = get_expected_sha256(model_card)
    actual_sha256 = calculate_sha256(weights_path)

    if actual_sha256 != expected_sha256:
        raise ClassifierArtifactError(
            "Classifier SHA-256 mismatch. "
            f"Expected {expected_sha256}, got {actual_sha256}."
        )

    test_top1 = get_test_top1(model_card)

    if test_top1 < settings.min_test_top1:
        raise ClassifierArtifactError(
            "Classifier test_top1 is below the configured minimum. "
            f"test_top1={test_top1}, min_test_top1={settings.min_test_top1}."
        )

    if not settings.classifier_labels:
        raise ClassifierArtifactError("settings.classifier_labels must not be empty.")

    return model_card


def load_and_verify_classifier(settings: Settings) -> nn.Module:
    """Load and verify the classifier model.

    This is the main function the API and worker should call at startup.

    Args:
        settings: Application settings.

    Returns:
        Loaded classifier model in eval mode on CPU.

    Raises:
        ClassifierArtifactError: If artifacts are invalid or model loading fails.
    """
    model_card = verify_classifier_artifacts(settings)

    backbone = get_backbone_name(model_card)
    num_classes = len(settings.classifier_labels)

    model = build_classifier_architecture(
        backbone=backbone,
        num_classes=num_classes,
    )

    state_dict = load_state_dict_safely(Path(settings.model_weights_path))

    try:
        model.load_state_dict(state_dict, strict=True)
    except RuntimeError as error:
        raise ClassifierArtifactError(
            "Classifier state_dict does not match the configured architecture. "
            f"Backbone={backbone}, num_classes={num_classes}."
        ) from error

    model.eval()

    for parameter in model.parameters():
        parameter.requires_grad = False

    return model


# Optional alias if other teammates prefer shorter naming.
load_and_verify = load_and_verify_classifier