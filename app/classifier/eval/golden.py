"""Golden set replay test.

Run as:
    pytest app/classifier/eval/golden.py -v

Pass criteria:
- Every image produces the byte-identical expected label.
- Top-1 confidence is within 1e-6 of the expected value.

Failure blocks CI — the golden-set-test job must pass before smoke tests run.
"""

import json
from pathlib import Path

from app.classifier.model import load_and_verify
from app.classifier.predict import classify_image
from app.config import get_settings

_GOLDEN_DIR = Path(__file__).parent / "golden_images"
_EXPECTED_FILE = Path(__file__).parent / "golden_expected.json"


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

    with _EXPECTED_FILE.open() as f:
        expected_items: list[dict[str, object]] = json.load(f)

    for item in expected_items:
        filename = str(item["filename"])
        expected_label = str(item["expected_label"])
        expected_confidence = float(str(item["expected_top1_confidence"]))

        image_bytes = (_GOLDEN_DIR / filename).read_bytes()
        result = classify_image(model, image_bytes, settings.classifier_labels)

        assert result.label == expected_label, (
            f"Label mismatch on {filename}: "
            f"expected '{expected_label}', got '{result.label}'"
        )
        assert abs(result.confidence - expected_confidence) < 1e-6, (
            f"Confidence mismatch on {filename}: "
            f"expected {expected_confidence:.8f}, got {result.confidence:.8f}"
        )
