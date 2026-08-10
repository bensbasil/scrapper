import pytest
import httpx
from api_server import app

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_api_status():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_running" in data
        assert isinstance(data["is_running"], bool)

@pytest.mark.anyio
async def test_api_businesses_pagination():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/businesses?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "businesses" in data
        assert data["limit"] == 5
        assert data["offset"] == 0

@pytest.mark.anyio
async def test_api_runs():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/runs?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "runs" in data
