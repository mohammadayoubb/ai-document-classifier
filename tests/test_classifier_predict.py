"""Unit tests for app.classifier.predict.

These tests verify:
- teammate-compatible classify_image() works
- PredictionResult shape matches the mock interface
- path prediction works
- bytes prediction works
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


def make_settings() -> Settings:
    """Create isolated test settings.

    _env_file=None prevents tests from reading the real project .env file.
    """
    return Settings(
        _env_file=None,
        database_url="sqlite:///test.db",
        vault_token="test-token",
        model_weights_path="fake/classifier.pt",
        model_card_path="fake/model_card.json",
        min_test_top1=0.80,
        classifier_labels=CLASSIFIER_LABELS,
        low_confidence_threshold=0.70,
    )


def make_test_image() -> Image.Image:
    """Create a simple RGB PIL image."""
    return Image.new("RGB", (300, 300), color=(255, 255, 255))


def make_test_image_bytes() -> bytes:
    """Create valid TIFF image bytes."""
    buffer = BytesIO()
    make_test_image().save(buffer, format="TIFF")
    return buffer.getvalue()


def make_invoice_logits() -> torch.Tensor:
    """Return logits where invoice is the strongest class."""
    logits = torch.zeros(len(CLASSIFIER_LABELS))
    logits[11] = 10.0  # invoice
    logits[15] = 2.0   # memo
    logits[1] = 1.0    # form
    return logits


def test_classify_image_returns_prediction_result() -> None:
    """classify_image should match teammate-compatible API."""
    model = FixedLogitsModel(make_invoice_logits())

    result = classifier_predict.classify_image(
        model=model,
        image_bytes=make_test_image_bytes(),
        labels=CLASSIFIER_LABELS,
    )

    assert isinstance(result, classifier_predict.PredictionResult)
    assert result.label == "invoice"
    assert result.confidence > 0.99
    assert result.top5_labels[0] == "invoice"
    assert result.top5_scores[0] == result.confidence
    assert len(result.top5_labels) == 5
    assert len(result.top5_scores) == 5


def test_prediction_result_to_dict_matches_expected_shape() -> None:
    """PredictionResult.to_dict should expose the expected response fields."""
    model = FixedLogitsModel(make_invoice_logits())

    result = classifier_predict.classify_image(
        model=model,
        image_bytes=make_test_image_bytes(),
        labels=CLASSIFIER_LABELS,
    ).to_dict()

    assert set(result.keys()) == {
        "label",
        "confidence",
        "top5_labels",
        "top5_scores",
    }
    assert result["label"] == "invoice"
    assert isinstance(result["confidence"], float)
    assert isinstance(result["top5_labels"], list)
    assert isinstance(result["top5_scores"], list)


def test_classify_image_with_uniform_logits_returns_valid_top5() -> None:
    """Even low-confidence logits should still return a valid PredictionResult."""
    logits = torch.zeros(len(CLASSIFIER_LABELS))
    model = FixedLogitsModel(logits)

    result = classifier_predict.classify_image(
        model=model,
        image_bytes=make_test_image_bytes(),
        labels=CLASSIFIER_LABELS,
    )

    assert isinstance(result.label, str)
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.top5_labels) == 5
    assert len(result.top5_scores) == 5


def test_predictor_predict_bytes_works() -> None:
    """ClassifierPredictor.predict_bytes should classify raw image bytes."""
    settings = make_settings()
    model = FixedLogitsModel(make_invoice_logits())

    predictor = classifier_predict.ClassifierPredictor(
        model=model,
        settings=settings,
        device="cpu",
    )

    result = predictor.predict_bytes(make_test_image_bytes())

    assert result.label == "invoice"
    assert result.confidence > 0.99
    assert result.top5_labels[0] == "invoice"


def test_predictor_predict_path_works(tmp_path: Path) -> None:
    """ClassifierPredictor.predict_path should classify a local image path."""
    image_path = tmp_path / "sample.tif"
    make_test_image().save(image_path, format="TIFF")

    settings = make_settings()
    model = FixedLogitsModel(make_invoice_logits())

    predictor = classifier_predict.ClassifierPredictor(
        model=model,
        settings=settings,
        device="cpu",
    )

    result = predictor.predict_path(image_path)

    assert result.label == "invoice"
    assert result.confidence > 0.99
    assert result.top5_labels[0] == "invoice"


def test_load_pil_image_from_path_rejects_missing_file(tmp_path: Path) -> None:
    """Missing image path should fail clearly."""
    missing_path = tmp_path / "missing.tif"

    with pytest.raises(
        classifier_predict.ClassifierPredictionError,
        match="Image file not found",
    ):
        classifier_predict.load_pil_image_from_path(missing_path)


def test_load_pil_image_from_bytes_rejects_empty_bytes() -> None:
    """Empty image bytes should fail clearly."""
    with pytest.raises(ValueError, match="image_bytes cannot be empty"):
        classifier_predict.load_pil_image_from_bytes(b"")


def test_load_pil_image_from_bytes_rejects_invalid_bytes() -> None:
    """Invalid image bytes should fail clearly."""
    with pytest.raises(ValueError, match="could not be decoded"):
        classifier_predict.load_pil_image_from_bytes(b"not a real image")


def test_classify_image_rejects_invalid_bytes() -> None:
    """classify_image should raise ValueError for invalid image bytes."""
    model = FixedLogitsModel(make_invoice_logits())

    with pytest.raises(ValueError, match="could not be decoded"):
        classifier_predict.classify_image(
            model=model,
            image_bytes=b"not a real image",
            labels=CLASSIFIER_LABELS,
        )


def test_validate_labels_rejects_empty_labels() -> None:
    """Empty labels should fail clearly."""
    with pytest.raises(ValueError, match="labels must not be empty"):
        classifier_predict.validate_labels([])


def test_validate_labels_rejects_duplicate_labels() -> None:
    """Duplicate labels should fail clearly."""
    with pytest.raises(ValueError, match="duplicate"):
        classifier_predict.validate_labels(["letter", "letter"])


def test_classify_image_rejects_empty_labels() -> None:
    """classify_image should validate labels before inference."""
    model = FixedLogitsModel(make_invoice_logits())

    with pytest.raises(ValueError, match="labels must not be empty"):
        classifier_predict.classify_image(
            model=model,
            image_bytes=make_test_image_bytes(),
            labels=[],
        )


def test_create_classifier_predictor_uses_verified_model_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_classifier_predictor should use model.load_and_verify."""
    settings = make_settings()
    model = FixedLogitsModel(make_invoice_logits())

    called = {"value": False}

    def fake_load_and_verify(received_settings: Settings) -> nn.Module:
        called["value"] = True
        assert received_settings is settings
        return model

    monkeypatch.setattr(
        classifier_predict,
        "load_and_verify",
        fake_load_and_verify,
    )

    predictor = classifier_predict.create_classifier_predictor(
        settings=settings,
        device="cpu",
    )

    result = predictor.predict_bytes(make_test_image_bytes())

    assert called["value"] is True
    assert result.label == "invoice"


def test_predict_image_path_convenience_function(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """predict_image_path should return a JSON-friendly dictionary."""
    image_path = tmp_path / "sample.tif"
    make_test_image().save(image_path, format="TIFF")

    settings = make_settings()
    model = FixedLogitsModel(make_invoice_logits())

    def fake_load_and_verify(received_settings: Settings) -> nn.Module:
        assert received_settings is settings
        return model

    monkeypatch.setattr(
        classifier_predict,
        "load_and_verify",
        fake_load_and_verify,
    )

    result = classifier_predict.predict_image_path(
        image_path=image_path,
        settings=settings,
        device="cpu",
    )

    assert result["label"] == "invoice"
    assert result["confidence"] > 0.99
    assert result["top5_labels"][0] == "invoice"
    assert len(result["top5_labels"]) == 5
    assert len(result["top5_scores"]) == 5


def test_predict_image_bytes_convenience_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """predict_image_bytes should return a JSON-friendly dictionary."""
    settings = make_settings()
    model = FixedLogitsModel(make_invoice_logits())

    def fake_load_and_verify(received_settings: Settings) -> nn.Module:
        assert received_settings is settings
        return model

    monkeypatch.setattr(
        classifier_predict,
        "load_and_verify",
        fake_load_and_verify,
    )

    result = classifier_predict.predict_image_bytes(
        image_bytes=make_test_image_bytes(),
        settings=settings,
        device="cpu",
    )

    assert result["label"] == "invoice"
    assert result["confidence"] > 0.99
    assert result["top5_labels"][0] == "invoice"
    assert len(result["top5_labels"]) == 5
    assert len(result["top5_scores"]) == 5


def test_classify_image_rejects_model_output_label_mismatch() -> None:
    """If model outputs more classes than labels, classify_image should fail clearly."""
    logits = torch.zeros(len(CLASSIFIER_LABELS))
    logits[15] = 10.0
    model = FixedLogitsModel(logits)

    too_few_labels = CLASSIFIER_LABELS[:10]

    with pytest.raises(
        classifier_predict.ClassifierPredictionError,
        match="class index does not match",
    ):
        classifier_predict.classify_image(
            model=model,
            image_bytes=make_test_image_bytes(),
            labels=too_few_labels,
        )