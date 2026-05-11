"""Inference latency benchmark over the 50 golden images.

Run after the stack is up:
    python scripts/benchmark.py

Outputs p50, p95, and p99 latency in milliseconds.
Warns if p95 > 1000ms and suggests switching to ConvNeXt Tiny if using Small.
"""

import json
import sys
import time
from pathlib import Path

GOLDEN_DIR = Path("app/classifier/eval/golden_images")
EXPECTED_FILE = Path("app/classifier/eval/golden_expected.json")
WARN_P95_MS = 1000.0


def run_benchmark() -> None:
    """Load the model, run inference over all golden images, and report latency stats."""
    from app.classifier.model import load_and_verify
    from app.classifier.predict import classify_image
    from app.config import get_settings

    settings = get_settings()
    model = load_and_verify(settings)

    with EXPECTED_FILE.open() as f:
        items: list[dict[str, object]] = json.load(f)

    if not items:
        print("golden_expected.json is empty — run after Member A commits the golden set.")
        sys.exit(0)

    latencies_ms: list[float] = []
    for item in items:
        image_bytes = (GOLDEN_DIR / str(item["filename"])).read_bytes()
        t0 = time.perf_counter()
        classify_image(model, image_bytes, settings.classifier_labels)
        latencies_ms.append((time.perf_counter() - t0) * 1000)

    latencies_ms.sort()
    n = len(latencies_ms)
    p50 = latencies_ms[int(n * 0.50)]
    p95 = latencies_ms[int(n * 0.95)]
    p99 = latencies_ms[int(n * 0.99)]

    print(f"Inference latency over {n} images:")
    print(f"  p50 = {p50:.1f} ms")
    print(f"  p95 = {p95:.1f} ms")
    print(f"  p99 = {p99:.1f} ms")

    if p95 > WARN_P95_MS:
        print(
            f"WARNING: p95 {p95:.0f}ms exceeds 1000ms target. "
            "Consider switching from ConvNeXt Small → Tiny."
        )


if __name__ == "__main__":
    run_benchmark()
