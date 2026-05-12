"""Unit tests for the inference worker overlay PNG generation.

Tests _generate_overlay() in isolation — no MinIO, DB, or model required.
All cases follow the Arrange → Act → Assert pattern.
"""

import io

from PIL import Image

from app.workers.inference import _generate_overlay


def _make_source_image(width: int = 224, height: int = 224) -> bytes:
    """Return raw PNG bytes of a blank grayscale image."""
    buf = io.BytesIO()
    Image.new("L", (width, height), color=180).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


def test_generate_overlay_returns_non_empty_bytes() -> None:
    """The overlay function must always return at least some bytes."""
    # Arrange
    source = _make_source_image()

    # Act
    result = _generate_overlay(source, "invoice", 0.91)

    # Assert
    assert len(result) > 0


def test_generate_overlay_returns_valid_png() -> None:
    """The returned bytes must be decodeable as a PNG by Pillow."""
    # Arrange
    source = _make_source_image()

    # Act
    result = _generate_overlay(source, "invoice", 0.91)

    # Assert — Pillow raises if bytes are not a valid image
    image = Image.open(io.BytesIO(result))
    assert image.format == "PNG"


def test_generate_overlay_output_is_rgb_mode() -> None:
    """Overlay converts grayscale source to RGB so the colour bar renders."""
    # Arrange
    source = _make_source_image()

    # Act
    result = _generate_overlay(source, "memo", 0.55)

    # Assert
    image = Image.open(io.BytesIO(result))
    assert image.mode == "RGB"


# ---------------------------------------------------------------------------
# Output dimensions
# ---------------------------------------------------------------------------


def test_generate_overlay_preserves_source_width() -> None:
    """Overlay must not change the image width."""
    # Arrange
    source = _make_source_image(width=320, height=240)

    # Act
    result = _generate_overlay(source, "letter", 0.80)

    # Assert
    image = Image.open(io.BytesIO(result))
    assert image.width == 320


def test_generate_overlay_preserves_source_height() -> None:
    """Overlay must not change the image height."""
    # Arrange
    source = _make_source_image(width=320, height=240)

    # Act
    result = _generate_overlay(source, "letter", 0.80)

    # Assert
    image = Image.open(io.BytesIO(result))
    assert image.height == 240


# ---------------------------------------------------------------------------
# Confidence bar colour logic
# ---------------------------------------------------------------------------


def test_generate_overlay_high_confidence_has_green_bottom_pixel() -> None:
    """High confidence (0.99) means nearly the full width is green at the bottom."""
    # Arrange
    source = _make_source_image(width=200, height=200)

    # Act
    result = _generate_overlay(source, "invoice", 0.99)

    # Assert — pixel near the centre-bottom should be green (0, ~180, 0)
    image = Image.open(io.BytesIO(result))
    pixels = image.load()
    assert pixels is not None
    # Sample the centre pixel on the bottom bar — should be green-dominant
    centre_x = image.width // 2
    bottom_y = image.height - 1
    r, g, b = pixels[centre_x, bottom_y]  # type: ignore[index]
    assert g > r and g > b, f"Expected green pixel, got RGB({r},{g},{b})"


def test_generate_overlay_zero_confidence_has_red_bottom_pixel() -> None:
    """Zero confidence means the entire bottom bar is red (no green fill)."""
    # Arrange
    source = _make_source_image(width=200, height=200)

    # Act
    result = _generate_overlay(source, "form", 0.0)

    # Assert — bottom bar should be entirely red
    image = Image.open(io.BytesIO(result))
    pixels = image.load()
    assert pixels is not None
    centre_x = image.width // 2
    bottom_y = image.height - 1
    r, g, b = pixels[centre_x, bottom_y]  # type: ignore[index]
    assert r > g and r > b, f"Expected red pixel, got RGB({r},{g},{b})"


# ---------------------------------------------------------------------------
# Accepts TIFF source (the real-world input format)
# ---------------------------------------------------------------------------


def test_generate_overlay_accepts_tiff_source() -> None:
    """Overlay must work on raw TIFF bytes, the actual scanner output format."""
    # Arrange
    buf = io.BytesIO()
    Image.new("L", (224, 224), color=150).save(buf, format="TIFF")
    tiff_source = buf.getvalue()

    # Act
    result = _generate_overlay(tiff_source, "resume", 0.75)

    # Assert
    image = Image.open(io.BytesIO(result))
    assert image.format == "PNG"
