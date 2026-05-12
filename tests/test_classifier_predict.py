"""Unit tests for app.classifier.predict.

These tests verify:
- PIL image prediction works
- path prediction works
- bytes prediction works
- low-confidence flag works
- invalid images fail clearly
- label validation works
- create_classifier_predictor uses the verified model loader
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
import torch
import torch.nn as nn
from PIL import Image

from app.config import Settings
from app.classifier import predict as classifier_predict


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


class FixedLogitsModel(nn.Module):
    """Tiny model that returns fixed logits for predictable tests."""

    def __init__(self, logits: torch.Tensor) -> None:
        super().__init__()
        self.register_buffer("fixed_logits", logits.float())

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size = x.shape[0]
        return self.fixed_logits.unsqueeze(0).repeat(batch_size, 1)


def make_settings(
    *,
    low_confidence_threshold: float = 0.70,
) -> Settings:
    return Settings(
        # Important: do not read the real .env during unit tests.
        _env_file=None,
        database_url="sqlite:///test.db",
        vault_token="test-token",
        model_weights_path="fake/classifier.pt",
        model_card_path="fake/model_card.json",
        min_test_top1=0.80,
        classifier_labels=CLASSIFIER_LABELS,
        low_confidence_threshold=low_confidence_threshold,
    )


def make_test_image() -> Image.Image:
    """Create a simple RGB PIL image."""
    return Image.new("RGB", (300, 300), color=(255, 255, 255))


def make_invoice_logits() -> torch.Tensor:
    """Return logits where invoice is the strongest class."""
    logits = torch.zeros(len(CLASSIFIER_LABELS))
    logits[11] = 10.0  # invoice
    logits[15] = 2.0   # memo
    logits[1] = 1.0    # form
    return logits


def test_predict_pil_image_returns_expected_top_prediction() -> None:
    settings = make_settings()
    model = FixedLogitsModel(make_invoice_logits())

    predictor = classifier_predict.ClassifierPredictor(
        model=model,
        settings=settings,
        device="cpu",
    )

    prediction = predictor.predict_pil_image(make_test_image())
    result = prediction.to_dict()

    assert result["label"] == "invoice"
    assert result["class_index"] == 11
    assert result["confidence"] > 0.99
    assert result["low_confidence"] is False
    assert len(result["top5"]) == 5
    assert result["top5"][0]["label"] == "invoice"
    assert result["top5"][0]["class_index"] == 11


def test_predict_pil_image_sets_low_confidence_flag() -> None:
    settings = make_settings(low_confidence_threshold=0.70)

    # Equal logits produce low confidence because softmax is spread across classes.
    logits = torch.zeros(len(CLASSIFIER_LABELS))
    model = FixedLogitsModel(logits)

    predictor = classifier_predict.ClassifierPredictor(
        model=model,
        settings=settings,
        device="cpu",
    )

    prediction = predictor.predict_pil_image(make_test_image())

    assert prediction.low_confidence is True
    assert prediction.confidence < settings.low_confidence_threshold
    assert len(prediction.top5) == 5


def test_predict_path_loads_image_and_predicts(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.tif"
    make_test_image().save(image_path, format="TIFF")

    settings = make_settings()
    model = FixedLogitsModel(make_invoice_logits())

    predictor = classifier_predict.ClassifierPredictor(
        model=model,
        settings=settings,
        device="cpu",
    )

    prediction = predictor.predict_path(image_path)

    assert prediction.label == "invoice"
    assert prediction.class_index == 11
    assert prediction.low_confidence is False


def test_predict_bytes_loads_image_and_predicts() -> None:
    buffer = BytesIO()
    make_test_image().save(buffer, format="TIFF")
    image_bytes = buffer.getvalue()

    settings = make_settings()
    model = FixedLogitsModel(make_invoice_logits())

    predictor = classifier_predict.ClassifierPredictor(
        model=model,
        settings=settings,
        device="cpu",
    )

    prediction = predictor.predict_bytes(image_bytes)

    assert prediction.label == "invoice"
    assert prediction.class_index == 11
    assert prediction.low_confidence is False


def test_load_pil_image_from_path_rejects_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.tif"

    with pytest.raises(
        classifier_predict.ClassifierPredictionError,
        match="Image file not found",
    ):
        classifier_predict.load_pil_image_from_path(missing_path)


def test_load_pil_image_from_bytes_rejects_empty_bytes() -> None:
    with pytest.raises(
        classifier_predict.ClassifierPredictionError,
        match="Image bytes are empty",
    ):
        classifier_predict.load_pil_image_from_bytes(b"")


def test_load_pil_image_from_bytes_rejects_invalid_bytes() -> None:
    with pytest.raises(
        classifier_predict.ClassifierPredictionError,
        match="Could not decode image bytes",
    ):
        classifier_predict.load_pil_image_from_bytes(b"not a real image")


def test_validate_labels_rejects_empty_labels() -> None:
    with pytest.raises(
        classifier_predict.ClassifierPredictionError,
        match="must not be empty",
    ):
        classifier_predict.validate_labels([])


def test_validate_labels_rejects_duplicate_labels() -> None:
    with pytest.raises(
        classifier_predict.ClassifierPredictionError,
        match="duplicate labels",
    ):
        classifier_predict.validate_labels(["letter", "letter"])


def test_create_classifier_predictor_uses_verified_model_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings()
    model = FixedLogitsModel(make_invoice_logits())

    called = {"value": False}

    def fake_load_and_verify_classifier(received_settings: Settings) -> nn.Module:
        called["value"] = True
        assert received_settings is settings
        return model

    monkeypatch.setattr(
        classifier_predict,
        "load_and_verify_classifier",
        fake_load_and_verify_classifier,
    )

    predictor = classifier_predict.create_classifier_predictor(
        settings=settings,
        device="cpu",
    )

    prediction = predictor.predict_pil_image(make_test_image())

    assert called["value"] is True
    assert prediction.label == "invoice"
    assert prediction.class_index == 11


def test_predict_image_path_convenience_function(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_path = tmp_path / "sample.tif"
    make_test_image().save(image_path, format="TIFF")

    settings = make_settings()
    model = FixedLogitsModel(make_invoice_logits())

    def fake_load_and_verify_classifier(received_settings: Settings) -> nn.Module:
        assert received_settings is settings
        return model

    monkeypatch.setattr(
        classifier_predict,
        "load_and_verify_classifier",
        fake_load_and_verify_classifier,
    )

    result = classifier_predict.predict_image_path(
        image_path=image_path,
        settings=settings,
        device="cpu",
    )

    assert result["label"] == "invoice"
    assert result["class_index"] == 11
    assert result["low_confidence"] is False
    assert len(result["top5"]) == 5


def test_predict_image_bytes_convenience_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buffer = BytesIO()
    make_test_image().save(buffer, format="TIFF")

    settings = make_settings()
    model = FixedLogitsModel(make_invoice_logits())

    def fake_load_and_verify_classifier(received_settings: Settings) -> nn.Module:
        assert received_settings is settings
        return model

    monkeypatch.setattr(
        classifier_predict,
        "load_and_verify_classifier",
        fake_load_and_verify_classifier,
    )

    result = classifier_predict.predict_image_bytes(
        image_bytes=buffer.getvalue(),
        settings=settings,
        device="cpu",
    )

    assert result["label"] == "invoice"
    assert result["class_index"] == 11
    assert result["low_confidence"] is False
    assert len(result["top5"]) == 5