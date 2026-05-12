"""Unit tests for the RQ JobQueue adapter.

All Redis and RQ calls are mocked — no real Redis instance required.
Tests verify that JobQueue constructs the correct RQ job payload and
returns the job ID to the caller.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.infra.queue import JobQueue


@pytest.fixture()
def queue() -> JobQueue:
    """Return a JobQueue with a mocked Redis connection and RQ Queue."""
    with patch("app.infra.queue.Redis") as mock_redis_class, \
         patch("app.infra.queue.Queue") as mock_queue_class:
        mock_redis_class.from_url.return_value = MagicMock()
        mock_queue_class.return_value = MagicMock()
        q = JobQueue(redis_url="redis://localhost:6379")
    return q


# ---------------------------------------------------------------------------
# enqueue_inference()
# ---------------------------------------------------------------------------


def test_enqueue_inference_returns_job_id() -> None:
    """enqueue_inference() must return the RQ job ID as a string."""
    # Arrange
    with patch("app.infra.queue.Redis"), patch("app.infra.queue.Queue") as mock_q_class:
        mock_job = MagicMock()
        mock_job.id = "abc-123"
        mock_q_class.return_value.enqueue.return_value = mock_job
        q = JobQueue(redis_url="redis://localhost:6379")

        # Act
        job_id = q.enqueue_inference(
            batch_id=1,
            filename="scan.tif",
            storage_key="documents/scan.tif",
            request_id="req-001",
        )

        # Assert
        assert job_id == "abc-123"


def test_enqueue_inference_targets_correct_worker_function() -> None:
    """enqueue_inference() must reference the exact job function path that RQ resolves."""
    # Arrange
    with patch("app.infra.queue.Redis"), patch("app.infra.queue.Queue") as mock_q_class:
        mock_job = MagicMock()
        mock_job.id = "xyz"
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job
        mock_q_class.return_value = mock_queue
        q = JobQueue(redis_url="redis://localhost:6379")

        # Act
        q.enqueue_inference(
            batch_id=5,
            filename="doc.tif",
            storage_key="documents/doc.tif",
            request_id="req-002",
        )

        # Assert
        positional_args = mock_queue.enqueue.call_args[0]
        assert positional_args[0] == "app.workers.inference.run_inference_job"


def test_enqueue_inference_passes_batch_id_to_job() -> None:
    """enqueue_inference() must forward batch_id as the first job argument."""
    # Arrange
    with patch("app.infra.queue.Redis"), patch("app.infra.queue.Queue") as mock_q_class:
        mock_job = MagicMock()
        mock_job.id = "xyz"
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job
        mock_q_class.return_value = mock_queue
        q = JobQueue(redis_url="redis://localhost:6379")

        # Act
        q.enqueue_inference(
            batch_id=42,
            filename="doc.tif",
            storage_key="documents/doc.tif",
            request_id="req-003",
        )

        # Assert
        positional_args = mock_queue.enqueue.call_args[0]
        assert positional_args[1] == 42  # batch_id is the second positional arg


def test_enqueue_inference_passes_filename_to_job() -> None:
    """enqueue_inference() must forward filename so the inference worker can create the Prediction row."""
    # Arrange
    with patch("app.infra.queue.Redis"), patch("app.infra.queue.Queue") as mock_q_class:
        mock_job = MagicMock()
        mock_job.id = "xyz"
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job
        mock_q_class.return_value = mock_queue
        q = JobQueue(redis_url="redis://localhost:6379")

        # Act
        q.enqueue_inference(
            batch_id=1,
            filename="invoice_2026.tif",
            storage_key="documents/invoice_2026.tif",
            request_id="req-004",
        )

        # Assert
        positional_args = mock_queue.enqueue.call_args[0]
        assert positional_args[2] == "invoice_2026.tif"


def test_enqueue_inference_passes_request_id_for_log_correlation() -> None:
    """enqueue_inference() must forward request_id so worker logs match ingest logs."""
    # Arrange
    with patch("app.infra.queue.Redis"), patch("app.infra.queue.Queue") as mock_q_class:
        mock_job = MagicMock()
        mock_job.id = "xyz"
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job
        mock_q_class.return_value = mock_queue
        q = JobQueue(redis_url="redis://localhost:6379")

        # Act
        q.enqueue_inference(
            batch_id=1,
            filename="scan.tif",
            storage_key="documents/scan.tif",
            request_id="trace-id-999",
        )

        # Assert
        positional_args = mock_queue.enqueue.call_args[0]
        assert "trace-id-999" in positional_args


def test_enqueue_inference_sets_job_timeout() -> None:
    """enqueue_inference() must set a 30-second timeout so stalled jobs are killed."""
    # Arrange
    with patch("app.infra.queue.Redis"), patch("app.infra.queue.Queue") as mock_q_class:
        mock_job = MagicMock()
        mock_job.id = "xyz"
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job
        mock_q_class.return_value = mock_queue
        q = JobQueue(redis_url="redis://localhost:6379")

        # Act
        q.enqueue_inference(
            batch_id=1,
            filename="scan.tif",
            storage_key="documents/scan.tif",
            request_id="req",
        )

        # Assert
        call_kwargs = mock_queue.enqueue.call_args[1]
        assert call_kwargs.get("job_timeout") == 30
