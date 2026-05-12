"""Unit tests for app.classifier.model.

These tests verify that classifier artifact loading:
- succeeds with valid weights/model card
- rejects missing weights
- rejects SHA-256 mismatch
- rejects low test_top1
- rejects unsupported backbone
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import torch
import torch.nn as nn

from app.config import Settings
from app.classifier import model as classifier_model


class TinyTestClassifier(nn.Module):
    """Tiny test model used instead of real ConvNeXt for fast unit tests."""

    def __init__(self, num_classes: int) -> None:
        super().__init__()
        self.flatten = nn.Flatten()
        self.classifier = nn.Linear(4, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.flatten(x)
        return self.classifier(x)


def calculate_sha256(path: Path) -> str:
    sha256 = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def make_settings(
    *,
    weights_path: Path,
    model_card_path: Path,
    min_test_top1: float = 0.80,
) -> Settings:
    return Settings(
        # Important for unit tests:
        # Do not load the real project .env file, because it may contain
        # docker/dev variables that are not part of Settings.
        _env_file=None,

        database_url="sqlite:///test.db",
        vault_token="test-token",
        model_weights_path=str(weights_path),
        model_card_path=str(model_card_path),
        min_test_top1=min_test_top1,
        classifier_labels=[
            "letter",
            "form",
            "email",
            "handwritten",
            "advertisement",
            "scientific_report",
            "scientific_publication",
            "specification",
            "file_folder",
            "news_article",
            "budget",
            "invoice",
            "presentation",
            "questionnaire",
            "resume",
            "memo",
        ],
    )


def write_model_card(
    *,
    path: Path,
    sha256: str,
    test_top1: float = 0.85,
    backbone: str = "convnext_tiny",
) -> None:
    model_card = {
        "sha256": sha256,
        "test_top1": test_top1,
        "test_top5": 0.97,
        "backbone": backbone,
        "artifact": {
            "filename": "classifier.pt",
            "sha256": sha256,
        },
        "metrics": {
            "test_top1": test_top1,
            "test_top5": 0.97,
        },
    }

    path.write_text(json.dumps(model_card), encoding="utf-8")


def save_test_weights(path: Path, num_classes: int = 16) -> None:
    model = TinyTestClassifier(num_classes=num_classes)
    torch.save(model.state_dict(), path)


def patch_build_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ConvNeXt building so tests do not instantiate the real model."""

    def fake_build_classifier_architecture(
        *,
        backbone: str,
        num_classes: int,
    ) -> nn.Module:
        if backbone not in {"convnext_tiny", "convnext_small"}:
            raise classifier_model.ClassifierArtifactError(
                f"Unsupported classifier backbone '{backbone}'."
            )

        return TinyTestClassifier(num_classes=num_classes)

    monkeypatch.setattr(
        classifier_model,
        "build_classifier_architecture",
        fake_build_classifier_architecture,
    )


def test_load_and_verify_classifier_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid artifacts should load successfully."""
    patch_build_classifier(monkeypatch)

    weights_path = tmp_path / "classifier.pt"
    model_card_path = tmp_path / "model_card.json"

    save_test_weights(weights_path)
    sha256 = calculate_sha256(weights_path)
    write_model_card(path=model_card_path, sha256=sha256, test_top1=0.85)

    settings = make_settings(
        weights_path=weights_path,
        model_card_path=model_card_path,
        min_test_top1=0.80,
    )

    model = classifier_model.load_and_verify_classifier(settings)

    assert isinstance(model, nn.Module)
    assert model.training is False
    assert all(parameter.requires_grad is False for parameter in model.parameters())


def test_verify_classifier_artifacts_rejects_missing_weights(tmp_path: Path) -> None:
    """Missing classifier.pt should fail before startup."""
    weights_path = tmp_path / "missing_classifier.pt"
    model_card_path = tmp_path / "model_card.json"

    write_model_card(path=model_card_path, sha256="fake-sha", test_top1=0.85)

    settings = make_settings(
        weights_path=weights_path,
        model_card_path=model_card_path,
        min_test_top1=0.80,
    )

    with pytest.raises(
        classifier_model.ClassifierArtifactError,
        match="Classifier weights not found",
    ):
        classifier_model.verify_classifier_artifacts(settings)


def test_verify_classifier_artifacts_rejects_sha_mismatch(tmp_path: Path) -> None:
    """If classifier.pt changes, SHA-256 verification should fail."""
    weights_path = tmp_path / "classifier.pt"
    model_card_path = tmp_path / "model_card.json"

    save_test_weights(weights_path)
    write_model_card(
        path=model_card_path,
        sha256="wrong-sha256",
        test_top1=0.85,
    )

    settings = make_settings(
        weights_path=weights_path,
        model_card_path=model_card_path,
        min_test_top1=0.80,
    )

    with pytest.raises(
        classifier_model.ClassifierArtifactError,
        match="Classifier SHA-256 mismatch",
    ):
        classifier_model.verify_classifier_artifacts(settings)


def test_verify_classifier_artifacts_rejects_low_test_top1(tmp_path: Path) -> None:
    """Model should fail if test_top1 is below configured minimum."""
    weights_path = tmp_path / "classifier.pt"
    model_card_path = tmp_path / "model_card.json"

    save_test_weights(weights_path)
    sha256 = calculate_sha256(weights_path)

    write_model_card(
        path=model_card_path,
        sha256=sha256,
        test_top1=0.75,
    )

    settings = make_settings(
        weights_path=weights_path,
        model_card_path=model_card_path,
        min_test_top1=0.80,
    )

    with pytest.raises(
        classifier_model.ClassifierArtifactError,
        match="below the configured minimum",
    ):
        classifier_model.verify_classifier_artifacts(settings)


def test_load_and_verify_classifier_rejects_unsupported_backbone(
    tmp_path: Path,
) -> None:
    """Unsupported backbone in model_card.json should fail."""
    weights_path = tmp_path / "classifier.pt"
    model_card_path = tmp_path / "model_card.json"

    save_test_weights(weights_path)
    sha256 = calculate_sha256(weights_path)

    write_model_card(
        path=model_card_path,
        sha256=sha256,
        test_top1=0.85,
        backbone="resnet50",
    )

    settings = make_settings(
        weights_path=weights_path,
        model_card_path=model_card_path,
        min_test_top1=0.80,
    )

    with pytest.raises(
        classifier_model.ClassifierArtifactError,
        match="Unsupported classifier backbone",
    ):
        classifier_model.load_and_verify_classifier(settings)


def test_load_model_card_rejects_invalid_json(tmp_path: Path) -> None:
    """Invalid model_card.json should fail clearly."""
    model_card_path = tmp_path / "model_card.json"
    model_card_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(
        classifier_model.ClassifierArtifactError,
        match="Model card is not valid JSON",
    ):
        classifier_model.load_model_card(model_card_path)