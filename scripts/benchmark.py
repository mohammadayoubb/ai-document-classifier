"""Latency benchmark for the README demo budgets.

Run after the stack is up for full API and end-to-end measurements:
    python scripts/benchmark.py

The script measures inference inside the app container. API and SFTP checks are
reported as SKIP when the Docker stack is not reachable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from math import ceil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

GOLDEN_DIR = Path("app/classifier/eval/golden_images")
EXPECTED_FILE = Path("app/classifier/eval/golden_expected.json")
DEFAULT_OUTPUT_FILE = PROJECT_ROOT / "frontend" / "public" / "latency-results.json"

API_BASE = os.getenv("BENCH_API_BASE", "http://localhost:8000")
BENCH_EMAIL = os.getenv("BENCH_EMAIL", "admin@example.com")
BENCH_PASSWORD = os.getenv("BENCH_PASSWORD", "a12345678")
BENCH_TOKEN = os.getenv("BENCH_TOKEN")
API_SERVICE = os.getenv("BENCH_API_SERVICE", "api")
REDIS_SERVICE = os.getenv("BENCH_REDIS_SERVICE", "redis")
SFTP_SERVICE = os.getenv("BENCH_SFTP_SERVICE", "sftp")
SFTP_UPLOAD_DIR = "/home/uploader/uploads"

API_SAMPLES = max(1, int(os.getenv("BENCH_API_SAMPLES", "30")))
E2E_SAMPLES = max(1, int(os.getenv("BENCH_E2E_SAMPLES", "3")))
POLL_INTERVAL_SECONDS = 0.5
E2E_TIMEOUT_SECONDS = 20.0
OUTPUT_FILE = Path(os.getenv("BENCH_OUTPUT_FILE", str(DEFAULT_OUTPUT_FILE)))

BUDGETS_MS = {
    "API cached reads": 50.0,
    "API uncached reads": 200.0,
    "Inference per document": 1000.0,
    "SFTP to GET /batches/{id}": 10000.0,
}

LOGIN_HINT = "Set BENCH_EMAIL/BENCH_PASSWORD to a valid user, or set BENCH_TOKEN."


@dataclass(frozen=True)
class MetricResult:
    """One measured latency metric for the demo table."""

    name: str
    budget_ms: float
    samples_ms: list[float]
    skipped_reason: str | None = None

    @property
    def p50_ms(self) -> float:
        return percentile(self.samples_ms, 50)

    @property
    def p95_ms(self) -> float:
        return percentile(self.samples_ms, 95)

    @property
    def p99_ms(self) -> float:
        return percentile(self.samples_ms, 99)

    @property
    def passed(self) -> bool:
        return self.skipped_reason is None and self.p95_ms < self.budget_ms

    def to_json(self) -> dict[str, object]:
        """Return a frontend-friendly JSON object for one benchmark metric."""
        return {
            "name": self.name,
            "budget_ms": self.budget_ms,
            "samples": len(self.samples_ms),
            "p50_ms": None if self.skipped_reason else round(self.p50_ms, 1),
            "p95_ms": None if self.skipped_reason else round(self.p95_ms, 1),
            "p99_ms": None if self.skipped_reason else round(self.p99_ms, 1),
            "status": "SKIP" if self.skipped_reason else "PASS" if self.passed else "FAIL",
            "reason": self.skipped_reason,
        }


def percentile(values: list[float], percentile_value: int) -> float:
    """Return nearest-rank percentile for a non-empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = ceil((percentile_value / 100) * len(ordered)) - 1
    index = max(0, min(len(ordered) - 1, rank))
    return ordered[index]


def docker_compose(*args: str, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    """Run one docker compose command from the project root."""
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def require_success(result: subprocess.CompletedProcess[str]) -> None:
    """Raise a compact error when a docker compose command fails."""
    if result.returncode == 0:
        return
    message = result.stderr.strip() or result.stdout.strip() or "docker compose command failed"
    raise RuntimeError(message.splitlines()[-1])


def api_request(
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    form: dict[str, str] | None = None,
    json_body: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, object]]:
    """Call the real API using only the Python standard library."""
    body: bytes | None = None
    request_headers = dict(headers or {})

    if form is not None:
        body = urllib.parse.urlencode(form).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return response.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        try:
            data = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            data = {"detail": payload}
        return exc.code, data


def time_request(path: str, headers: dict[str, str]) -> float:
    """Time one authenticated GET request and return milliseconds."""
    started = time.perf_counter()
    status, body = api_request(path, headers=headers)
    if status >= 400:
        raise RuntimeError(f"GET {path} failed with status {status}: {body.get('detail', '')}")
    return (time.perf_counter() - started) * 1000


def run_inference_benchmark() -> MetricResult:
    """Measure classifier latency inside the Docker app container."""
    code = r"""
import json
import time
from pathlib import Path

from app.classifier.model import load_and_verify
from app.classifier.predict import classify_image
from app.config import get_settings

golden_dir = Path("app/classifier/eval/golden_images")
expected_file = Path("app/classifier/eval/golden_expected.json")
settings = get_settings()
model = load_and_verify(settings)

with expected_file.open() as f:
    items = json.load(f)

latencies_ms = []
for item in items:
    image_bytes = (golden_dir / str(item["filename"])).read_bytes()
    started = time.perf_counter()
    classify_image(model, image_bytes, settings.classifier_labels)
    latencies_ms.append((time.perf_counter() - started) * 1000)

print("BENCHMARK_JSON=" + json.dumps({"samples_ms": latencies_ms}))
"""
    result = docker_compose("exec", "-T", API_SERVICE, "python", "-c", code, timeout=300.0)
    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or "app container unavailable"
        return MetricResult(
            name="Inference per document",
            budget_ms=BUDGETS_MS["Inference per document"],
            samples_ms=[],
            skipped_reason=compact_error_text(reason),
        )

    marker = "BENCHMARK_JSON="
    for line in reversed(result.stdout.splitlines()):
        if line.startswith(marker):
            payload = json.loads(line.removeprefix(marker))
            samples = [float(value) for value in payload["samples_ms"]]
            break
    else:
        return MetricResult(
            name="Inference per document",
            budget_ms=BUDGETS_MS["Inference per document"],
            samples_ms=[],
            skipped_reason="Inference container did not return benchmark JSON",
        )

    return MetricResult(
        name="Inference per document",
        budget_ms=BUDGETS_MS["Inference per document"],
        samples_ms=samples,
    )


def login() -> str:
    """Login or register the benchmark user, then return a JWT token."""
    if BENCH_TOKEN:
        return BENCH_TOKEN

    status, body = api_request(
        "/auth/jwt/login",
        method="POST",
        form={"username": BENCH_EMAIL, "password": BENCH_PASSWORD},
    )
    if status == 200:
        return str(body["access_token"])

    register_status, _ = api_request(
        "/auth/register",
        method="POST",
        json_body={"email": BENCH_EMAIL, "password": BENCH_PASSWORD},
    )
    if register_status not in {200, 201, 400}:
        raise RuntimeError(
            f"Register failed for {BENCH_EMAIL} with status {register_status}. {LOGIN_HINT}"
        )

    retry_status, retry_body = api_request(
        "/auth/jwt/login",
        method="POST",
        form={"username": BENCH_EMAIL, "password": BENCH_PASSWORD},
    )
    if retry_status != 200:
        raise RuntimeError(
            f"Login failed for {BENCH_EMAIL} with status {retry_status}. {LOGIN_HINT}"
        )
    return str(retry_body["access_token"])


def delete_batch_list_cache() -> None:
    """Delete Redis keys for cached GET /batches pages via the Redis container."""
    scan = docker_compose(
        "exec",
        "-T",
        REDIS_SERVICE,
        "redis-cli",
        "--scan",
        "--pattern",
        "docclassifier:batches:list*",
    )
    require_success(scan)
    keys = [line.strip() for line in scan.stdout.splitlines() if line.strip()]
    if not keys:
        return

    for index in range(0, len(keys), 100):
        delete = docker_compose(
            "exec",
            "-T",
            REDIS_SERVICE,
            "redis-cli",
            "del",
            *keys[index:index + 100],
        )
        require_success(delete)


def run_api_cached_benchmark(headers: dict[str, str]) -> MetricResult:
    """Warm GET /batches once, then measure cached read latency."""
    time_request("/batches?limit=100&offset=0", headers)
    samples = [
        time_request("/batches?limit=100&offset=0", headers)
        for _ in range(API_SAMPLES)
    ]
    return MetricResult(
        name="API cached reads",
        budget_ms=BUDGETS_MS["API cached reads"],
        samples_ms=samples,
    )


def run_api_uncached_benchmark(headers: dict[str, str]) -> MetricResult:
    """Clear batch-list cache before every GET /batches request."""
    samples: list[float] = []
    for _ in range(API_SAMPLES):
        delete_batch_list_cache()
        samples.append(time_request("/batches?limit=100&offset=0", headers))
    return MetricResult(
        name="API uncached reads",
        budget_ms=BUDGETS_MS["API uncached reads"],
        samples_ms=samples,
    )


def prepare_sftp_dropzone() -> None:
    """Make the demo SFTP upload volume writable by the configured SFTP user."""
    owner = docker_compose(
        "exec",
        "-T",
        SFTP_SERVICE,
        "chown",
        "1000:100",
        SFTP_UPLOAD_DIR,
    )
    require_success(owner)

    mode = docker_compose(
        "exec",
        "-T",
        SFTP_SERVICE,
        "chmod",
        "775",
        SFTP_UPLOAD_DIR,
    )
    require_success(mode)


def upload_sftp_file(local_path: Path, remote_filename: str) -> None:
    """Copy one file into the SFTP drop zone through Docker Compose."""
    remote_path = f"{SFTP_UPLOAD_DIR}/{remote_filename}"
    result = docker_compose(
        "cp",
        str(local_path),
        f"{SFTP_SERVICE}:{remote_path}",
        timeout=30.0,
    )
    require_success(result)

    owner = docker_compose(
        "exec",
        "-T",
        SFTP_SERVICE,
        "chown",
        "1000:100",
        remote_path,
    )
    require_success(owner)

    mode = docker_compose(
        "exec",
        "-T",
        SFTP_SERVICE,
        "chmod",
        "664",
        remote_path,
    )
    require_success(mode)


def cleanup_latency_sftp_files() -> None:
    """Remove benchmark-owned SFTP files so old runs cannot be reprocessed."""
    prepare_sftp_dropzone()
    for directory in (
        SFTP_UPLOAD_DIR,
        f"{SFTP_UPLOAD_DIR}/processed",
        f"{SFTP_UPLOAD_DIR}/quarantine",
    ):
        result = docker_compose(
            "exec",
            "-T",
            SFTP_SERVICE,
            "find",
            directory,
            "-maxdepth",
            "1",
            "-type",
            "f",
            "-name",
            "latency_*",
            "-delete",
        )
        if result.returncode != 0 and "No such file" not in result.stderr:
            require_success(result)


def cleanup_latency_rq_jobs() -> None:
    """Remove queued benchmark-owned RQ jobs left by interrupted demo runs."""
    code = r"""
from redis import Redis
from rq import Queue

redis = Redis.from_url("redis://redis:6379")
queue = Queue(connection=redis)
removed = 0
for job_id in queue.get_job_ids():
    job = queue.fetch_job(job_id)
    if job is None:
        continue
    if any(isinstance(arg, str) and arg.startswith("latency_") for arg in job.args):
        job.delete()
        removed += 1
print(f"removed={removed}")
"""
    result = docker_compose("exec", "-T", API_SERVICE, "python", "-c", code)
    require_success(result)


def find_completed_sftp_batch(
    headers: dict[str, str],
    filename: str,
) -> int | None:
    """Return the batch id once the uploaded filename is completed and visible."""
    list_status, list_body = api_request(
        "/batches?limit=100&offset=0",
        headers=headers,
    )
    if list_status >= 400:
        raise RuntimeError(
            f"GET /batches failed with status {list_status}: {list_body.get('detail', '')}"
        )

    for batch in list_body.get("items", []):
        if not isinstance(batch, dict):
            continue
        batch_id = batch.get("id")
        if batch_id is None:
            continue
        detail_status, detail = api_request(
            f"/batches/{batch_id}",
            headers=headers,
        )
        if detail_status >= 400:
            raise RuntimeError(
                f"GET /batches/{batch_id} failed with status {detail_status}: "
                f"{detail.get('detail', '')}"
            )
        if detail.get("status") != "completed":
            continue
        for prediction in detail.get("predictions", []):
            if not isinstance(prediction, dict):
                continue
            if prediction.get("filename") == filename:
                return int(batch_id)
    return None


def run_e2e_benchmark(headers: dict[str, str]) -> MetricResult:
    """Measure SFTP drop to completed GET /batches/{id} visibility."""
    with EXPECTED_FILE.open() as f:
        items: list[dict[str, object]] = json.load(f)
    if not items:
        return MetricResult(
            name="SFTP to GET /batches/{id}",
            budget_ms=BUDGETS_MS["SFTP to GET /batches/{id}"],
            samples_ms=[],
            skipped_reason="golden_expected.json is empty",
        )

    source_path = GOLDEN_DIR / str(items[0]["filename"])
    samples: list[float] = []
    cleanup_latency_rq_jobs()
    cleanup_latency_sftp_files()
    try:
        for _ in range(E2E_SAMPLES):
            remote_filename = f"latency_{uuid.uuid4().hex}_{source_path.name}"
            started = time.perf_counter()
            upload_sftp_file(source_path, remote_filename)

            deadline = time.perf_counter() + E2E_TIMEOUT_SECONDS
            while time.perf_counter() < deadline:
                batch_id = find_completed_sftp_batch(headers, remote_filename)
                if batch_id is not None:
                    samples.append((time.perf_counter() - started) * 1000)
                    break
                time.sleep(POLL_INTERVAL_SECONDS)
            else:
                raise TimeoutError(
                    f"{remote_filename} was not completed within {E2E_TIMEOUT_SECONDS:.0f}s"
                )
    finally:
        cleanup_latency_sftp_files()

    return MetricResult(
        name="SFTP to GET /batches/{id}",
        budget_ms=BUDGETS_MS["SFTP to GET /batches/{id}"],
        samples_ms=samples,
    )


def run_stack_benchmarks() -> list[MetricResult]:
    """Measure API and E2E budgets when the Docker stack is reachable."""
    try:
        health_status, health_body = api_request("/health", timeout=2.0)
        if health_status >= 400:
            raise RuntimeError(
                f"GET /health failed with status {health_status}: "
                f"{health_body.get('detail', '')}"
            )
        token = login()
        headers = {"Authorization": f"Bearer {token}"}

        results: list[MetricResult] = []
        try:
            results.append(run_api_cached_benchmark(headers))
        except Exception as exc:
            results.append(
                MetricResult(
                    name="API cached reads",
                    budget_ms=BUDGETS_MS["API cached reads"],
                    samples_ms=[],
                    skipped_reason=compact_error(exc),
                )
            )

        try:
            results.append(run_api_uncached_benchmark(headers))
        except Exception as exc:
            results.append(
                MetricResult(
                    name="API uncached reads",
                    budget_ms=BUDGETS_MS["API uncached reads"],
                    samples_ms=[],
                    skipped_reason=compact_error(exc),
                )
            )

        try:
            results.append(run_e2e_benchmark(headers))
        except Exception as exc:
            results.append(
                MetricResult(
                    name="SFTP to GET /batches/{id}",
                    budget_ms=BUDGETS_MS["SFTP to GET /batches/{id}"],
                    samples_ms=[],
                    skipped_reason=compact_error(exc),
                )
            )
        return results
    except Exception as exc:
        reason = compact_error(exc, prefix="API stack unavailable")
        return [
            MetricResult(
                name="API cached reads",
                budget_ms=BUDGETS_MS["API cached reads"],
                samples_ms=[],
                skipped_reason=reason,
            ),
            MetricResult(
                name="API uncached reads",
                budget_ms=BUDGETS_MS["API uncached reads"],
                samples_ms=[],
                skipped_reason=reason,
            ),
            MetricResult(
                name="SFTP to GET /batches/{id}",
                budget_ms=BUDGETS_MS["SFTP to GET /batches/{id}"],
                samples_ms=[],
                skipped_reason=reason,
            ),
        ]


def compact_error_text(message: str, prefix: str | None = None) -> str:
    """Return one line of text suitable for the latency table."""
    message = message.splitlines()[0] if message else "unknown error"
    if prefix:
        return f"{prefix}: {message}"
    return message


def compact_error(exc: Exception, prefix: str | None = None) -> str:
    """Return a one-line error suitable for the latency table."""
    return compact_error_text(str(exc), prefix)


def print_results(results: list[MetricResult]) -> None:
    """Print a concise demo table with PASS/FAIL/SKIP status."""
    print("\nLatency budget demo")
    print("-" * 91)
    print(
        f"{'Metric':<28} {'N':>3} {'p50':>9} {'p95':>9} "
        f"{'p99':>9} {'Budget':>9} Result"
    )
    print("-" * 91)

    for result in results:
        if result.skipped_reason is not None:
            print(
                f"{result.name:<28} {0:>3} {'-':>9} {'-':>9} {'-':>9} "
                f"{result.budget_ms:>7.0f}ms SKIP"
            )
            print(f"  reason: {result.skipped_reason}")
            continue

        status = "PASS" if result.passed else "FAIL"
        print(
            f"{result.name:<28} {len(result.samples_ms):>3} "
            f"{result.p50_ms:>7.1f}ms {result.p95_ms:>7.1f}ms "
            f"{result.p99_ms:>7.1f}ms {result.budget_ms:>7.0f}ms {status}"
        )


def write_results_json(results: list[MetricResult]) -> None:
    """Write the latest benchmark result for the Admin UI."""
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "scripts/benchmark.py",
        "items": [result.to_json() for result in results],
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote UI results to {OUTPUT_FILE}")


def run_benchmark() -> None:
    """Run all available latency measurements and exit non-zero on failures."""
    inference_result = run_inference_benchmark()
    results = [inference_result, *run_stack_benchmarks()]
    print_results(results)
    write_results_json(results)

    failures = [
        result for result in results if result.skipped_reason is None and not result.passed
    ]
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    run_benchmark()
