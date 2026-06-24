"""헬스체크 엔드포인트 테스트."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient) -> None:
    """GET /health — 프로세스 생존 확인."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_health_includes_correlation_id(client: AsyncClient) -> None:
    """응답에 X-Request-ID 헤더가 포함되는지 확인."""
    response = await client.get("/health")
    assert "X-Request-ID" in response.headers
