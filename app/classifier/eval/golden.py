"""Golden set replay test.

Run as:
    uv run pytest app/classifier/eval/golden.py -v

Pass criteria:
- Every image produces the exact expected label.
- Top-1 confidence is within 1e-6 of the expected value.

Failure blocks CI — the golden-set-test job must pass before smoke tests run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.classifier.model import load_and_verify
from app.classifier.predict import classify_image
from app.config import get_settings

_GOLDEN_DIR = Path(__file__).parent / "golden_images"
_EXPECTED_FILE = Path(__file__).parent / "golden_expected.json"
_CONFIDENCE_TOLERANCE = 1e-6


def load_expected_items() -> list[dict[str, Any]]:
    """Load and validate golden_expected.json."""
    if not _EXPECTED_FILE.exists():
        raise AssertionError(f"Golden expected file not found: {_EXPECTED_FILE}")

    if not _EXPECTED_FILE.is_file():
        raise AssertionError(f"Golden expected path is not a file: {_EXPECTED_FILE}")

    with _EXPECTED_FILE.open("r", encoding="utf-8") as file:
        expected_items = json.load(file)

    if not isinstance(expected_items, list):
        raise AssertionError("golden_expected.json must contain a list.")

    if not expected_items:
        raise AssertionError("golden_expected.json is empty.")

    return expected_items


def validate_expected_item(item: dict[str, Any], index: int) -> None:
    """Validate one golden_expected.json item."""
    required_keys = {
        "filename",
        "expected_label",
        "expected_top1_confidence",
    }

    missing_keys = required_keys - set(item.keys())

    if missing_keys:
        raise AssertionError(
            f"Golden item at index {index} is missing keys: {sorted(missing_keys)}"
        )

    if not isinstance(item["filename"], str) or not item["filename"]:
        raise AssertionError(f"Golden item at index {index} has invalid filename.")

    if not isinstance(item["expected_label"], str) or not item["expected_label"]:
        raise AssertionError(f"Golden item at index {index} has invalid expected_label.")

    try:
        float(item["expected_top1_confidence"])
    except (TypeError, ValueError) as error:
        raise AssertionError(
            f"Golden item at index {index} has invalid expected_top1_confidence."
        ) from error


def test_golden_set() -> None:
    """Verify classifier output matches the committed golden expectations.

    Each of the 50 golden images must produce:
    - The exact expected label string
    - A top-1 confidence within 1e-6 of the expected value

    Raises:
        AssertionError: On any label mismatch or confidence deviation.
    """
    settings = get_settings()
    model = load_and_verify(settings)

    if not _GOLDEN_DIR.exists():
        raise AssertionError(f"Golden images directory not found: {_GOLDEN_DIR}")

    if not _GOLDEN_DIR.is_dir():
        raise AssertionError(f"Golden images path is not a directory: {_GOLDEN_DIR}")

    expected_items = load_expected_items()
    failures: list[str] = []

    for index, item in enumerate(expected_items):
        validate_expected_item(item, index)

        filename = str(item["filename"])
        expected_label = str(item["expected_label"])
        expected_confidence = float(item["expected_top1_confidence"])

        image_path = _GOLDEN_DIR / filename

        if not image_path.exists():
            failures.append(f"{filename}: missing golden image at {image_path}")
            continue

        image_bytes = image_path.read_bytes()
        result = classify_image(model, image_bytes, settings.classifier_labels)

        if result.label != expected_label:
            failures.append(
                f"{filename}: label mismatch. "
                f"expected '{expected_label}', got '{result.label}'"
            )
            continue

        confidence_diff = abs(result.confidence - expected_confidence)

        if confidence_diff > _CONFIDENCE_TOLERANCE:
            failures.append(
                f"{filename}: confidence mismatch. "
                f"expected {expected_confidence:.10f}, "
                f"got {result.confidence:.10f}, "
                f"diff {confidence_diff:.10f}, "
                f"tolerance {_CONFIDENCE_TOLERANCE}"
            )

    if failures:
        failure_preview = "\n".join(failures[:10])
        raise AssertionError(
            f"Golden set replay failed on {len(failures)} / {len(expected_items)} images.\n"
            f"First failures:\n{failure_preview}"
        )

    assert len(expected_items) == 50, (
        f"Expected 50 golden items, got {len(expected_items)}"
    )