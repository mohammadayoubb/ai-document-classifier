# ruff: noqa: S101, S106
import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.infra.cache import CacheAdapter
from app.services.prediction_service import PredictionService

NOW = datetime(2026, 5, 12, tzinfo=UTC)


def make_settings() -> Settings:
    return Settings(
        vault_root_token="root",
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/test",
        classifier_labels=["invoice", "form", "email"],
        low_confidence_threshold=0.7,
        cache_ttl_recent=15,
    )


def make_prediction(
    prediction_id: int = 1,
    confidence: float = 0.4,
    is_relabeled: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=prediction_id,
        batch_id=9,
        filename="invoice.pdf",
        storage_key="raw/invoice.pdf",
        overlay_key=None,
        predicted_label="invoice",
        confidence=confidence,
        top5_labels=json.dumps(["invoice", "form"]),
        top5_scores=json.dumps([confidence, 1 - confidence]),
        is_relabeled=is_relabeled,
        relabeled_to=None,
        relabeled_by=None,
        created_at=NOW,
    )


class FakePredictionRepo:
    def __init__(self, prediction: SimpleNamespace | None = None) -> None:
        self.prediction = prediction or make_prediction()
        self.recent = [self.prediction]
        self.relabel_calls = 0
        self.get_calls = 0
        self.list_recent_calls = 0
        self.create_kwargs: dict[str, object] | None = None

    async def list_recent(
        self,
        limit: int,
        only_needs_review: bool,
        low_confidence_threshold: float,
    ) -> list[SimpleNamespace]:
        self.list_recent_calls += 1
        return self.recent[:limit]

    async def get_by_id(self, pred_id: int) -> SimpleNamespace | None:
        self.get_calls += 1
        return self.prediction if pred_id == self.prediction.id else None

    async def relabel(
        self,
        pred_id: int,
        new_label: str,
        relabeled_by: int,
    ) -> SimpleNamespace | None:
        self.relabel_calls += 1
        prediction = await self.get_by_id(pred_id)
        if prediction is None:
            return None
        prediction.is_relabeled = True
        prediction.relabeled_to = new_label
        prediction.relabeled_by = relabeled_by
        return prediction

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.create_kwargs = kwargs
        return make_prediction(
            prediction_id=2,
            confidence=float(kwargs["confidence"]),
        )

    async def update_overlay_key(self, pred_id: int, overlay_key: str) -> SimpleNamespace:
        self.prediction.overlay_key = overlay_key
        return self.prediction


def test_recent_predictions_read_from_cache_when_present() -> None:
    async def exercise() -> None:
        repo = FakePredictionRepo()
        cache = CacheAdapter(prefix="test")
        service = PredictionService(repo, cache, settings=make_settings())
        key = cache.recent_predictions_key(20, False)
        await cache.set_json(key, {"items": [], "total": 0, "limit": 20})

        result = await service.list_recent()

        assert result.total == 0
        assert repo.list_recent_calls == 0

    asyncio.run(exercise())


def test_high_confidence_relabel_is_rejected() -> None:
    async def exercise() -> None:
        repo = FakePredictionRepo(make_prediction(confidence=0.91))
        service = PredictionService(repo, CacheAdapter(prefix="test"), settings=make_settings())

        with pytest.raises(ValueError, match="Only low-confidence"):
            await service.relabel(1, "form", actor_id=7)

        assert repo.relabel_calls == 0

    asyncio.run(exercise())


def test_invalid_corrected_label_is_rejected() -> None:
    async def exercise() -> None:
        repo = FakePredictionRepo()
        service = PredictionService(repo, CacheAdapter(prefix="test"), settings=make_settings())

        with pytest.raises(ValueError, match="not a configured classifier label"):
            await service.relabel(1, "not-a-label", actor_id=7)

        assert repo.get_calls == 0
        assert repo.relabel_calls == 0

    asyncio.run(exercise())


def test_successful_relabel_calls_repo_and_invalidates_related_caches() -> None:
    async def exercise() -> None:
        repo = FakePredictionRepo(make_prediction(confidence=0.31))
        cache = CacheAdapter(prefix="test")
        service = PredictionService(repo, cache, settings=make_settings())
        await cache.set_json(cache.recent_predictions_key(20, False), {"cached": True})
        await cache.set_json(cache.batch_list_key(None, 100, 0), {"cached": True})
        await cache.set_json(cache.batch_detail_key(9), {"cached": True})

        result = await service.relabel(1, "form", actor_id=7)

        assert repo.relabel_calls == 1
        assert result.is_relabeled is True
        assert result.relabeled_to == "form"
        assert await cache.get_json(cache.recent_predictions_key(20, False)) is None
        assert await cache.get_json(cache.batch_list_key(None, 100, 0)) is None
        assert await cache.get_json(cache.batch_detail_key(9)) is None

    asyncio.run(exercise())


def test_relabel_accepts_same_label_as_human_confirmation() -> None:
    async def exercise() -> None:
        repo = FakePredictionRepo(make_prediction(confidence=0.31))
        service = PredictionService(repo, CacheAdapter(prefix="test"), settings=make_settings())

        result = await service.relabel(1, "invoice", actor_id=7)

        assert repo.relabel_calls == 1
        assert result.is_relabeled is True
        assert result.relabeled_to == result.predicted_label
        assert result.needs_review is False

    asyncio.run(exercise())


def test_worker_prediction_creation_marks_low_confidence_as_review_needed() -> None:
    async def exercise() -> None:
        repo = FakePredictionRepo()
        cache = CacheAdapter(prefix="test")
        service = PredictionService(repo, cache, settings=make_settings())
        await cache.set_json(cache.batch_list_key(None, 100, 0), {"cached": True})

        result = await service.create_prediction_from_worker(
            batch_id=9,
            filename="invoice.pdf",
            storage_key="raw/invoice.pdf",
            predicted_label="invoice",
            confidence=0.42,
            top5_labels=["invoice", "form"],
            top5_scores=[0.42, 0.31],
        )

        assert result.needs_review is True
        assert repo.create_kwargs is not None
        assert json.loads(str(repo.create_kwargs["top5_labels"])) == ["invoice", "form"]
        assert await cache.get_json(cache.batch_list_key(None, 100, 0)) is None

    asyncio.run(exercise())


def test_relabel_raises_lookup_error_for_nonexistent_prediction() -> None:
    async def exercise() -> None:
        repo = FakePredictionRepo(make_prediction(confidence=0.3))
        service = PredictionService(repo, CacheAdapter(prefix="test"), settings=make_settings())

        with pytest.raises(LookupError, match="not found"):
            await service.relabel(9999, "form", actor_id=7)

    asyncio.run(exercise())


def test_relabel_at_exactly_threshold_confidence_is_rejected() -> None:
    """Confidence equal to the threshold is NOT low-confidence — relabeling is blocked."""
    async def exercise() -> None:
        repo = FakePredictionRepo(make_prediction(confidence=0.7))
        service = PredictionService(repo, CacheAdapter(prefix="test"), settings=make_settings())

        with pytest.raises(ValueError, match="low-confidence"):
            await service.relabel(1, "form", actor_id=7)

        assert repo.relabel_calls == 0

    asyncio.run(exercise())


def test_list_recent_cache_miss_queries_repo_and_populates_cache() -> None:
    async def exercise() -> None:
        repo = FakePredictionRepo()
        cache = CacheAdapter(prefix="test")
        service = PredictionService(repo, cache, settings=make_settings())

        result = await service.list_recent(limit=5)

        assert repo.list_recent_calls == 1
        assert result.limit == 5
        cached = await cache.get_json(cache.recent_predictions_key(5, False))
        assert cached is not None

    asyncio.run(exercise())


def test_list_recent_with_only_needs_review_uses_separate_cache_key() -> None:
    async def exercise() -> None:
        repo = FakePredictionRepo()
        cache = CacheAdapter(prefix="test")
        service = PredictionService(repo, cache, settings=make_settings())

        await service.list_recent(limit=20, only_needs_review=True)

        # The "review" key should be populated; the "all" key should not
        assert await cache.get_json(cache.recent_predictions_key(20, True)) is not None
        assert await cache.get_json(cache.recent_predictions_key(20, False)) is None

    asyncio.run(exercise())


def test_update_overlay_key_calls_repo_and_invalidates_caches() -> None:
    async def exercise() -> None:
        repo = FakePredictionRepo(make_prediction(confidence=0.4))
        cache = CacheAdapter(prefix="test")
        service = PredictionService(repo, cache, settings=make_settings())
        await cache.set_json(cache.recent_predictions_key(20, False), {"cached": True})
        await cache.set_json(cache.batch_detail_key(9), {"cached": True})

        result = await service.update_overlay_key(1, "overlays/scan.png")

        assert result.overlay_key == "overlays/scan.png"
        assert await cache.get_json(cache.recent_predictions_key(20, False)) is None
        assert await cache.get_json(cache.batch_detail_key(9)) is None

    asyncio.run(exercise())


def test_create_prediction_from_worker_raises_when_no_label_or_result_provided() -> None:
    async def exercise() -> None:
        repo = FakePredictionRepo()
        service = PredictionService(repo, CacheAdapter(prefix="test"), settings=make_settings())

        with pytest.raises(ValueError, match="predicted_label and confidence"):
            await service.create_prediction_from_worker(
                batch_id=1,
                filename="doc.tif",
                storage_key="documents/doc.tif",
            )

    asyncio.run(exercise())


def test_create_prediction_from_worker_accepts_prediction_result_object() -> None:
    """Service can extract fields from an arbitrary prediction_result object."""
    from types import SimpleNamespace

    async def exercise() -> None:
        repo = FakePredictionRepo()
        cache = CacheAdapter(prefix="test")
        service = PredictionService(repo, cache, settings=make_settings())
        prediction_result = SimpleNamespace(
            label="invoice",
            confidence=0.65,
            top5_labels=["invoice", "form"],
            top5_scores=[0.65, 0.35],
        )

        result = await service.create_prediction_from_worker(
            batch_id=9,
            filename="scan.tif",
            storage_key="documents/scan.tif",
            prediction_result=prediction_result,
        )

        assert result.needs_review is True  # 0.65 < 0.7 threshold

    asyncio.run(exercise())
