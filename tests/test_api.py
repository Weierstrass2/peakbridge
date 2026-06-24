"""API 통합 테스트."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_envelope(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("app.api.v1.sensors.SensorService")
async def test_sensors_readings_response_format(
    mock_service_cls: AsyncMock, client: AsyncClient
) -> None:
    """POST /sensors/readings — envelope 응답 형식 검증."""
    mock_instance = AsyncMock()
    mock_instance.record_reading.return_value = {
        "status": "recorded",
        "peak_triggered": False,
        "forecast_next_hour": [{"time": "2026-01-01T00:00:00", "predicted_current": 10.0}],
    }
    mock_service_cls.return_value = mock_instance

    response = await client.post(
        "/api/v1/sensors/readings",
        json={
            "device_id": "grid-001",
            "sensor_type": "grid_current",
            "value": 12.5,
            "unit": "A",
            "building_id": "building-001",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "data" in body
    assert "timestamp" in body
    assert body["data"]["status"] == "recorded"
    assert "peak_triggered" in body["data"]
    assert "forecast_next_hour" in body["data"]


@pytest.mark.asyncio
@patch("app.api.v1.dashboard.ForecastService")
@patch("app.api.v1.dashboard.EnergyRepository")
@patch("app.api.v1.dashboard.AlertRepository")
@patch("app.api.v1.dashboard.DeviceRepository")
@patch("app.api.v1.dashboard.SensorRepository")
async def test_dashboard_response_format(
    mock_sensor_repo: AsyncMock,
    mock_device_repo: AsyncMock,
    mock_alert_repo: AsyncMock,
    mock_energy_repo: AsyncMock,
    mock_forecast_svc: AsyncMock,
    client: AsyncClient,
) -> None:
    """GET /dashboard/{building_id} — 응답 필드 검증."""
    from datetime import datetime, timezone

    grid_reading = AsyncMock()
    grid_reading.value = 12.0
    ess_reading = AsyncMock()
    ess_reading.value = 65.0

    mock_sensor_repo.return_value.get_latest_by_building = AsyncMock(
        side_effect=[grid_reading, ess_reading]
    )
    mock_device_repo.return_value.list_by_building = AsyncMock(return_value=[])
    mock_alert_repo.return_value.has_active_peak = AsyncMock(return_value=False)
    mock_energy_repo.return_value.get_by_date = AsyncMock(return_value=None)
    mock_energy_repo.return_value.get_month_total = AsyncMock(return_value=0.0)
    mock_forecast_svc.return_value.get_next_hour_summary = AsyncMock(return_value=[])

    response = await client.get("/api/v1/dashboard/building-001")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    required_fields = [
        "grid_current",
        "ess_soc",
        "peak_active",
        "peak_threshold",
        "chargers",
        "forecast",
        "today_saved_won",
        "month_saved_won",
        "co2_reduced_kg",
        "last_updated",
    ]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"
