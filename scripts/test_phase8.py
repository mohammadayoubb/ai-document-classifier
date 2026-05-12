"""Phase 8 smoke tests — run these to verify your infra adapters work.

Usage (from project root):
    .venv/Scripts/python scripts/test_phase8.py

Requires: docker compose up (db, redis, minio, sftp, vault already running).
Does NOT require the classifier.pt model file.
"""

import asyncio
import io
import os
import sys

# Set required env vars BEFORE any app imports so Settings() can construct.
# These mirror what docker-compose injects into containers at runtime.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/docclassifier",
)
os.environ.setdefault("VAULT_TOKEN", "root")

# -- helpers ------------------------------------------------------------------

PASS = "\033[92m PASS\033[0m"
FAIL = "\033[91m FAIL\033[0m"


def section(title: str) -> None:
    print(f"\n{'-'*60}")
    print(f"  {title}")
    print(f"{'-'*60}")


def ok(msg: str) -> None:
    print(f"  {PASS}  {msg}")


def fail(msg: str, err: str) -> None:
    print(f"  {FAIL}  {msg}")
    print(f"         {err}")


# -- Test 1: Vault secrets -----------------------------------------------------

def test_vault() -> bool:
    section("Test 1 — Vault: resolve secrets")
    try:
        from app.infra.vault import VaultClient
        vault = VaultClient(addr="http://localhost:8200", token="root")
        assert vault.is_reachable(), "Vault not reachable"
        ok("Vault is reachable")

        sftp_pass = vault.get_secret("app", "sftp_password")
        assert sftp_pass == "password", f"Expected 'password', got '{sftp_pass}'"
        ok(f"sftp_password = '{sftp_pass}'")

        minio_key = vault.get_secret("app", "minio_secret_key")
        assert minio_key == "minioadmin", f"Expected 'minioadmin', got '{minio_key}'"
        ok(f"minio_secret_key = '{minio_key}'")

        jwt_key = vault.get_secret("app", "jwt_signing_key")
        assert len(jwt_key) == 64, "jwt_signing_key looks wrong"
        ok(f"jwt_signing_key = '{jwt_key[:8]}...' (64 hex chars)")

        return True
    except Exception as e:
        fail("Vault test failed", str(e))
        return False


# -- Test 2: SFTP adapter ------------------------------------------------------

def test_sftp() -> bool:
    section("Test 2 — SFTP: connect + list uploads/")
    try:
        from app.infra.sftp import SftpAdapter
        sftp = SftpAdapter(host="localhost", port=2222, username="uploader", password="password")
        sftp.connect()
        ok("Connected to SFTP at localhost:2222")

        files = sftp.list_uploads()
        ok(f"uploads/ contains {len(files)} file(s): {files or '(empty)'}")

        sftp.disconnect()
        ok("Disconnected cleanly")
        return True
    except Exception as e:
        fail("SFTP test failed", str(e))
        return False


# -- Test 3: MinIO blob adapter ------------------------------------------------

async def _test_blob_async() -> bool:
    from app.infra.blob import BlobStorage
    blob = BlobStorage(endpoint="localhost:9000", access_key="minioadmin", secret_key="minioadmin")

    test_data = b"hello from phase 8 test"
    test_key = "test/phase8_smoke.txt"

    await blob.upload("documents", test_key, test_data, "text/plain")
    ok(f"Uploaded {len(test_data)} bytes to documents/{test_key}")

    downloaded = await blob.download("documents", test_key)
    assert downloaded == test_data, "Download mismatch"
    ok(f"Downloaded {len(downloaded)} bytes — content matches OK")

    url = await blob.get_presigned_url("documents", test_key, expires_seconds=60)
    assert url.startswith("http"), f"Bad URL: {url}"
    ok(f"Pre-signed URL: {url[:60]}...")

    return True


def test_blob() -> bool:
    section("Test 3 — MinIO BlobStorage: upload / download / presigned URL")
    try:
        result = asyncio.run(_test_blob_async())
        return result
    except Exception as e:
        fail("Blob test failed", str(e))
        return False


# -- Test 4: Queue adapter -----------------------------------------------------

def test_queue() -> bool:
    section("Test 4 — RQ JobQueue: enqueue inference job")
    try:
        from app.infra.queue import JobQueue
        queue = JobQueue(redis_url="redis://localhost:6379")

        job_id = queue.enqueue_inference(
            batch_id=9999,
            filename="smoke_test.tif",
            storage_key="documents/smoke_test.tif",
            request_id="test-request-id-001",
        )
        assert job_id, "No job ID returned"
        ok(f"Job enqueued — id={job_id}")
        ok("(Job will stay queued — no inference worker running yet, model not loaded)")
        return True
    except Exception as e:
        fail("Queue test failed", str(e))
        return False


# -- Test 5: Validation logic --------------------------------------------------

def test_validation() -> bool:
    section("Test 5 — _validate_file: zero-byte / non-image / too-large / valid PNG")
    try:
        # Import directly — no infra needed
        sys.path.insert(0, ".")
        from app.workers.ingest import _validate_file
        from PIL import Image

        # zero-byte
        reason = _validate_file("empty.tif", b"")
        assert reason == "empty_file", f"Got: {reason}"
        ok("Zero-byte file -> 'empty_file'")

        # non-image
        reason = _validate_file("bad.tif", b"this is not an image at all!")
        assert reason == "invalid_format", f"Got: {reason}"
        ok("Non-image bytes -> 'invalid_format'")

        # too large (mock — just check size gate, don't allocate 50 MB)
        big = b"x" * (50 * 1024 * 1024 + 1)
        reason = _validate_file("big.tif", big)
        assert reason == "file_too_large", f"Got: {reason}"
        ok("51 MB file -> 'file_too_large'")

        # valid PNG
        buf = io.BytesIO()
        Image.new("L", (64, 64), color=128).save(buf, format="PNG")
        valid_png = buf.getvalue()
        reason = _validate_file("doc.png", valid_png)
        assert reason is None, f"Got: {reason}"
        ok("Valid 64×64 PNG -> None (accepted)")

        return True
    except Exception as e:
        fail("Validation test failed", str(e))
        return False


# -- Test 6: Overlay generation ------------------------------------------------

def test_overlay() -> bool:
    section("Test 6 — _generate_overlay: draw label + confidence bar")
    try:
        from PIL import Image
        from app.workers.inference import _generate_overlay

        buf = io.BytesIO()
        Image.new("L", (224, 224), color=200).save(buf, format="PNG")
        source = buf.getvalue()

        overlay = _generate_overlay(source, "invoice", 0.92)
        assert len(overlay) > 0, "Empty overlay"

        result_img = Image.open(io.BytesIO(overlay))
        assert result_img.mode == "RGB"
        ok(f"Overlay PNG generated — {len(overlay)} bytes, mode={result_img.mode}, size={result_img.size}")
        ok("Label 'invoice' + 92% confidence bar drawn")
        return True
    except Exception as e:
        fail("Overlay test failed", str(e))
        return False


# -- Test 7: SCP a file + verify it appears in SFTP ----------------------------

def test_sftp_drop() -> bool:
    section("Test 7 — SCP a synthetic TIFF -> verify it appears in uploads/")
    try:
        import io as _io
        from PIL import Image
        from app.infra.sftp import SftpAdapter

        # Build a tiny valid TIFF in memory
        buf = _io.BytesIO()
        Image.new("L", (64, 64), color=100).save(buf, format="TIFF")
        tiff_bytes = buf.getvalue()

        sftp = SftpAdapter(host="localhost", port=2222, username="uploader", password="password")
        sftp.connect()

        # Upload directly via paramiko putfo (simulates SCP drop)
        assert sftp._sftp is not None
        buf.seek(0)
        sftp._sftp.putfo(buf, "uploads/smoke_drop.tif")
        ok(f"Dropped smoke_drop.tif ({len(tiff_bytes)} bytes) into uploads/")

        files = sftp.list_uploads()
        assert "smoke_drop.tif" in files, f"File not visible in uploads/: {files}"
        ok(f"uploads/ now contains: {files}")

        # Clean up — move to processed so it doesn't linger
        sftp.move_to_processed("smoke_drop.tif")
        ok("Moved to processed/ (cleanup)")

        sftp.disconnect()
        return True
    except Exception as e:
        fail("SFTP drop test failed", str(e))
        return False


# -- main ----------------------------------------------------------------------

def main() -> None:
    print("\n" + "=" * 60)
    print("  Phase 8 Smoke Tests — Document Classifier Pipeline")
    print("=" * 60)

    results = [
        ("Vault secrets",       test_vault()),
        ("SFTP adapter",        test_sftp()),
        ("MinIO BlobStorage",   test_blob()),
        ("RQ JobQueue",         test_queue()),
        ("Ingest validation",   test_validation()),
        ("Overlay generation",  test_overlay()),
        ("SFTP file drop",      test_sftp_drop()),
    ]

    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    for name, ok_flag in results:
        status = "\033[92mOK\033[0m" if ok_flag else "\033[91mXX\033[0m"
        print(f"  {status}  {name}")
    print(f"\n  {passed}/{len(results)} passed\n")


if __name__ == "__main__":
    main()
