"""pytest configuration and shared fixtures."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    """Test HTTP client — MQTT/DB/scheduler mocked."""
    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch("app.main.mqtt_publisher.connect", new_callable=AsyncMock),
        patch("app.main.mqtt_subscriber.start", new_callable=AsyncMock),
        patch("app.main.mqtt_subscriber.stop", new_callable=AsyncMock),
        patch("app.main.mqtt_publisher.disconnect", new_callable=AsyncMock),
        patch("app.main.setup_scheduler"),
        patch("app.main.shutdown_scheduler"),
        patch("app.main.close_db", new_callable=AsyncMock),
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
