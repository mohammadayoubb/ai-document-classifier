"""CI smoke check — login then poll GET /batches until a prediction appears or timeout.

Called from the CI smoke-test job after an SFTP drop:
    python scripts/smoke_check.py

Exits 0 if a batch with at least one prediction appears within TIMEOUT_SECONDS.
Exits 1 on timeout.
"""

import sys
import time

import httpx

API_BASE = "http://localhost:8000"
TIMEOUT_SECONDS = 15
POLL_INTERVAL = 1.0
TEST_EMAIL = "test@test.com"
TEST_PASSWORD = "TestPass123!"


def get_token() -> str:
    """Login with the test account and return the JWT access token.

    Returns:
        Bearer JWT string.

    Raises:
        httpx.HTTPStatusError: If login fails.
    """
    response = httpx.post(
        f"{API_BASE}/auth/jwt/login",
        data={"username": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=10.0,
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def smoke_check() -> None:
    """Poll GET /batches until at least one batch has a prediction, or timeout."""
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.monotonic() + TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{API_BASE}/batches", headers=headers, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                if items and any(item.get("prediction_count", 0) > 0 for item in items):
                    print(f"Smoke check passed — {len(items)} batch(es) found with predictions")
                    return
        except httpx.RequestError:
            pass
        time.sleep(POLL_INTERVAL)

    print(
        "Smoke check timed out — no prediction appeared within "
        f"{TIMEOUT_SECONDS} seconds",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    smoke_check()
