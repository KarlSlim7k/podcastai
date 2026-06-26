"""Integration tests for the system endpoints."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_health_returns_healthy(client):
    resp = await client.get("/api/v1/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_status_returns_cuda_info(client):
    with patch("app.services.ai_service.ai_service.check_availability", new_callable=AsyncMock) as mock_ol:
        mock_ol.return_value = (True, ["qwen3:8b", "gemma3"])
        resp = await client.get("/api/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "cuda_available" in data
    assert "whisper_available" in data
    assert "ollama_available" in data
    assert "ollama_models" in data
    assert "llamacpp_available" in data
    assert "llamacpp_models" in data


@pytest.mark.asyncio
async def test_status_with_ollama_up(client):
    with patch("app.services.ai_service.ai_service.check_availability", new_callable=AsyncMock) as mock_ol:
        mock_ol.return_value = (True, ["qwen3:8b"])
        resp = await client.get("/api/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ollama_available"] is True
    assert "qwen3:8b" in data["ollama_models"]


@pytest.mark.asyncio
async def test_status_with_ollama_down(client):
    with patch("app.services.ai_service.ai_service.check_availability", new_callable=AsyncMock) as mock_ol:
        mock_ol.return_value = (False, [])
        resp = await client.get("/api/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ollama_available"] is False
    assert data["ollama_models"] == []


@pytest.mark.asyncio
async def test_models_returns_list(client):
    fake_models = [
        {"name": "qwen3:8b", "size": 5_000_000_000, "modified_at": "2026-01-01T00:00:00Z"},
        {"name": "gemma3", "size": 4_000_000_000, "modified_at": "2026-01-02T00:00:00Z"},
    ]
    with patch("app.services.ai_service.ai_service.list_models", new_callable=AsyncMock) as mock_lm:
        mock_lm.return_value = fake_models
        resp = await client.get("/api/v1/system/models")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "qwen3:8b"


@pytest.mark.asyncio
async def test_models_empty_when_ollama_down(client):
    with patch("app.services.ai_service.ai_service.list_models", new_callable=AsyncMock) as mock_lm:
        mock_lm.return_value = []
        resp = await client.get("/api/v1/system/models")
    assert resp.status_code == 200
    assert resp.json() == []
