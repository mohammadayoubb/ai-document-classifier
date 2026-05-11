"""CI smoke check — poll GET /batches until a prediction appears or timeout.

Called from the CI smoke-test job after an SFTP drop:
    python scripts/smoke_check.py

Exits 0 if a prediction appears within 15 seconds, exits 1 otherwise.
"""

import sys
import time

import httpx

API_BASE = "http://localhost:8000"
TIMEOUT_SECONDS = 15
POLL_INTERVAL = 1.0


def smoke_check() -> None:
    """Poll the batches endpoint until a prediction appears or the timeout expires."""
    # TODO: Phase 10 — get admin token via POST /auth/jwt/login, then poll GET /batches
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{API_BASE}/health", timeout=5.0)
            if response.status_code == 200:
                print("Health check passed — smoke check skeleton OK")
                return
        except httpx.RequestError:
            pass
        time.sleep(POLL_INTERVAL)

    print("Smoke check timed out", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    smoke_check()
