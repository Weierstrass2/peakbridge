"""피크 감지 로직 단위 테스트."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.peak_service import PeakService


@pytest.fixture
def peak_service() -> PeakService:
    """Mock 세션 기반 PeakService."""
    session = AsyncMock()
    return PeakService(session, mqtt=None)


class TestPeakDetection:
    """경계값 테스트 — 임계치 15A (> 비교)."""

    def test_below_threshold(self, peak_service: PeakService) -> None:
        assert peak_service.is_peak(14.9) is False

    def test_at_threshold(self, peak_service: PeakService) -> None:
        assert peak_service.is_peak(15.0) is False

    def test_above_threshold(self, peak_service: PeakService) -> None:
        assert peak_service.is_peak(15.1) is True

    def test_threshold_value(self, peak_service: PeakService) -> None:
        assert peak_service.threshold == 15.0


@pytest.mark.asyncio
async def test_evaluate_triggers_peak(peak_service: PeakService) -> None:
    """15.1A → 피크 감지 트리거."""
    peak_service.reset_state("bld-001")
    peak_service.alert_repo.create = AsyncMock()
    peak_service.alert_repo.resolve_all_peak = AsyncMock(return_value=0)
    peak_service.device_repo.list_by_building = AsyncMock(return_value=[])
    peak_service.control_repo.create = AsyncMock()
    peak_service.energy_repo.increment_savings = AsyncMock()

    result = await peak_service.evaluate("bld-001", 15.1, 50.0)
    assert result["peak_triggered"] is True
    assert result["peak_active"] is True
    peak_service.alert_repo.create.assert_called()


@pytest.mark.asyncio
async def test_evaluate_no_peak_below_threshold(peak_service: PeakService) -> None:
    """14.9A → 피크 미감지."""
    peak_service.reset_state("bld-002")
    peak_service.alert_repo.create = AsyncMock()

    result = await peak_service.evaluate("bld-002", 14.9, 50.0)
    assert result["peak_triggered"] is False
    assert result["peak_active"] is False
