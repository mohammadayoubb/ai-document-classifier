"""Unit tests for app.classifier.model.

These tests verify that classifier artifact loading:
- succeeds with valid weights/model card
- keeps teammate-compatible load_and_verify(settings)
- rejects missing weights
- rejects missing model card
- rejects SHA-256 mismatch
- rejects low test_top1
- rejects unsupported backbone
- rejects invalid JSON
- rejects duplicate labels
- rejects state_dict architecture mismatch
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


CLASSIFIER_LABELS = [
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
]


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
    """Calculate SHA-256 hash for a test file."""
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
    classifier_labels: list[str] | None = None,
) -> Settings:
    """Create isolated test settings.

    _env_file=None is important because unit tests should not read the real
    project .env file. The real .env may contain Docker/Vault variables that
    are not relevant to this unit test.
    """
    return Settings(
        _env_file=None,
        database_url="sqlite:///test.db",
        vault_token="test-token",
        model_weights_path=str(weights_path),
        model_card_path=str(model_card_path),
        min_test_top1=min_test_top1,
        classifier_labels=classifier_labels or CLASSIFIER_LABELS,
    )


def write_model_card(
    *,
    path: Path,
    sha256: str,
    test_top1: float = 0.85,
    backbone: str = "convnext_tiny",
    nested_only: bool = False,
) -> None:
    """Write a minimal model_card.json for tests."""
    if nested_only:
        model_card = {
            "artifact": {
                "sha256": sha256,
            },
            "metrics": {
                "test_top1": test_top1,
                "test_top5": 0.97,
            },
            "model": {
                "backbone": backbone,
            },
        }
    else:
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
            "model": {
                "backbone": backbone,
            },
        }

    path.write_text(json.dumps(model_card), encoding="utf-8")


def save_test_weights(path: Path, num_classes: int = 16) -> None:
    """Save a tiny test model state_dict."""
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


def test_load_and_verify_compatibility_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teammate-compatible load_and_verify(settings) should still work."""
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

    model = classifier_model.load_and_verify(settings)

    assert isinstance(model, nn.Module)
    assert model.training is False


def test_verify_classifier_artifacts_accepts_nested_model_card_fields(
    tmp_path: Path,
) -> None:
    """Model card may store sha/test_top1/backbone in nested sections."""
    weights_path = tmp_path / "classifier.pt"
    model_card_path = tmp_path / "model_card.json"

    save_test_weights(weights_path)
    sha256 = calculate_sha256(weights_path)
    write_model_card(
        path=model_card_path,
        sha256=sha256,
        test_top1=0.85,
        backbone="convnext_tiny",
        nested_only=True,
    )

    settings = make_settings(
        weights_path=weights_path,
        model_card_path=model_card_path,
        min_test_top1=0.80,
    )

    model_card = classifier_model.verify_classifier_artifacts(settings)

    assert classifier_model.get_expected_sha256(model_card) == sha256
    assert classifier_model.get_test_top1(model_card) == 0.85
    assert classifier_model.get_backbone_name(model_card) == "convnext_tiny"


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


def test_load_model_card_rejects_missing_model_card(tmp_path: Path) -> None:
    """Missing model_card.json should fail clearly."""
    model_card_path = tmp_path / "missing_model_card.json"

    with pytest.raises(
        classifier_model.ClassifierArtifactError,
        match="Model card not found",
    ):
        classifier_model.load_model_card(model_card_path)


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
        match="SHA-256 mismatch",
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
        match="Model top-1",
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


def test_validate_classifier_labels_rejects_empty_labels() -> None:
    """Empty label list should fail."""
    with pytest.raises(
        classifier_model.ClassifierArtifactError,
        match="must not be empty",
    ):
        classifier_model.validate_classifier_labels([])


def test_validate_classifier_labels_rejects_duplicate_labels() -> None:
    """Duplicate labels should fail."""
    with pytest.raises(
        classifier_model.ClassifierArtifactError,
        match="duplicate labels",
    ):
        classifier_model.validate_classifier_labels(["letter", "letter"])


def test_load_and_verify_classifier_rejects_state_dict_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A state_dict with wrong classifier shape should fail."""
    patch_build_classifier(monkeypatch)

    weights_path = tmp_path / "classifier.pt"
    model_card_path = tmp_path / "model_card.json"

    # Save weights for 8 classes, but settings has 16 labels.
    save_test_weights(weights_path, num_classes=8)
    sha256 = calculate_sha256(weights_path)

    write_model_card(
        path=model_card_path,
        sha256=sha256,
        test_top1=0.85,
        backbone="convnext_tiny",
    )

    settings = make_settings(
        weights_path=weights_path,
        model_card_path=model_card_path,
        min_test_top1=0.80,
        classifier_labels=CLASSIFIER_LABELS,
    )

    with pytest.raises(
        classifier_model.ClassifierArtifactError,
        match="state_dict does not match",
    ):
        classifier_model.load_and_verify_classifier(settings)