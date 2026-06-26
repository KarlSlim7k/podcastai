"""Unit tests for app.services.broll_service.

Covers the pure helpers (``_filter_mock_brolls``, ``brolls_to_json``) plus
``extract_keywords`` / ``search_pexels`` / ``suggest_brolls`` with
``ai_service.generate`` and ``httpx.AsyncClient`` mocked out — no real
Ollama or Pexels calls.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.broll_service import (
    _MOCK_BROLLS,
    BrollSuggestion,
    _filter_mock_brolls,
    brolls_to_json,
    extract_keywords,
    search_pexels,
    suggest_brolls,
)


# ── _filter_mock_brolls ───────────────────────────────────────────────────────

class TestFilterMockBrolls:
    def test_substring_match(self):
        result = _filter_mock_brolls("technology")
        assert any(b.id == "mock-3" for b in result)

    def test_partial_keyword_matches_via_substring(self):
        # "tech" is a substring of the mock's "technology" keyword.
        result = _filter_mock_brolls("tech")
        assert any(b.id == "mock-3" for b in result)

    def test_no_match_returns_generic_first_three(self):
        result = _filter_mock_brolls("xyznotakeyword")
        assert result == _MOCK_BROLLS[:3]

    def test_returns_at_most_three(self):
        result = _filter_mock_brolls("a")  # matches many via substring
        assert len(result) <= 3


# ── brolls_to_json ────────────────────────────────────────────────────────────

class TestBrollsToJson:
    def test_empty_list(self):
        assert brolls_to_json([]) == "[]"

    def test_round_trips_fields(self):
        s = BrollSuggestion(
            id="x1", kind="photo", keyword="nature",
            thumb_url="http://t", full_url="http://f",
            photographer="Jane", source="mock",
        )
        parsed = json.loads(brolls_to_json([s]))
        assert parsed == [{
            "id": "x1", "kind": "photo", "keyword": "nature",
            "thumb_url": "http://t", "full_url": "http://f",
            "photographer": "Jane", "source": "mock", "duration_s": 0.0,
        }]


# ── extract_keywords ──────────────────────────────────────────────────────────

class TestExtractKeywords:
    @pytest.mark.asyncio
    async def test_parses_json_array_response(self):
        with patch("app.services.broll_service.ai_service.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '["mountain", "city", "Sunset"]'
            result = await extract_keywords("algo de viajes y ciudades")
        assert result == ["mountain", "city", "sunset"]

    @pytest.mark.asyncio
    async def test_extracts_array_from_surrounding_text(self):
        with patch("app.services.broll_service.ai_service.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = 'Here are the keywords:\n["chess", "office"]\nDone.'
            result = await extract_keywords("ajedrez y oficinas")
        assert result == ["chess", "office"]

    @pytest.mark.asyncio
    async def test_ai_service_exception_falls_back(self):
        with patch("app.services.broll_service.ai_service.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = RuntimeError("ollama unreachable")
            result = await extract_keywords("cualquier cosa")
        assert result == ["abstract", "business"]

    @pytest.mark.asyncio
    async def test_empty_array_falls_back(self):
        with patch("app.services.broll_service.ai_service.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "[]"
            result = await extract_keywords("cualquier cosa")
        assert result == ["abstract", "business"]

    @pytest.mark.asyncio
    async def test_non_string_list_falls_back(self):
        with patch("app.services.broll_service.ai_service.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "[1, 2, 3]"
            result = await extract_keywords("cualquier cosa")
        assert result == ["abstract", "business"]


# ── search_pexels ─────────────────────────────────────────────────────────────

def _mock_async_client(response):
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestSearchPexels:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_empty(self, monkeypatch):
        monkeypatch.setattr("app.services.broll_service.settings.pexels_api_key", "")
        result = await search_pexels("technology")
        assert result == []

    @pytest.mark.asyncio
    async def test_successful_response_parsed(self, monkeypatch):
        monkeypatch.setattr("app.services.broll_service.settings.pexels_api_key", "fake-key")
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "photos": [{
                "id": 42, "photographer": "Jane Doe",
                "src": {"tiny": "http://thumb", "original": "http://full"},
            }]
        }
        with patch("app.services.broll_service.httpx.AsyncClient", return_value=_mock_async_client(fake_response)):
            result = await search_pexels("technology", per_page=3)
        assert len(result) == 1
        assert result[0].id == "42"
        assert result[0].source == "pexels"
        assert result[0].photographer == "Jane Doe"
        assert result[0].thumb_url == "http://thumb"
        assert result[0].full_url == "http://full"

    @pytest.mark.asyncio
    async def test_non_200_status_returns_empty(self, monkeypatch):
        monkeypatch.setattr("app.services.broll_service.settings.pexels_api_key", "fake-key")
        fake_response = MagicMock()
        fake_response.status_code = 401
        with patch("app.services.broll_service.httpx.AsyncClient", return_value=_mock_async_client(fake_response)):
            result = await search_pexels("technology")
        assert result == []

    @pytest.mark.asyncio
    async def test_client_exception_returns_empty(self, monkeypatch):
        monkeypatch.setattr("app.services.broll_service.settings.pexels_api_key", "fake-key")
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("network down"))
        with patch("app.services.broll_service.httpx.AsyncClient", return_value=ctx):
            result = await search_pexels("technology")
        assert result == []


# ── suggest_brolls (orchestration) ────────────────────────────────────────────

class TestSuggestBrolls:
    @pytest.mark.asyncio
    async def test_no_key_uses_mock_and_pads_to_at_least_six(self, monkeypatch):
        monkeypatch.setattr("app.services.broll_service.settings.pexels_api_key", "")
        with patch("app.services.broll_service.extract_keywords", new_callable=AsyncMock) as mock_kw:
            mock_kw.return_value = ["nature"]
            result = await suggest_brolls("un video sobre la naturaleza")
        assert len(result) >= 6
        assert all(r.source == "mock" for r in result)

    @pytest.mark.asyncio
    async def test_real_key_with_results_uses_pexels(self, monkeypatch):
        monkeypatch.setattr("app.services.broll_service.settings.pexels_api_key", "fake-key")
        pexels_result = [BrollSuggestion(
            id="p1", kind="photo", keyword="nature",
            thumb_url="http://t", full_url="http://f",
            photographer="Jane", source="pexels",
        )]
        with patch("app.services.broll_service.extract_keywords", new_callable=AsyncMock) as mock_kw, \
             patch("app.services.broll_service.search_pexels", new_callable=AsyncMock) as mock_search:
            mock_kw.return_value = ["nature"]
            mock_search.return_value = pexels_result
            result = await suggest_brolls("un video sobre la naturaleza")
        assert len(result) == 1
        assert result[0].source == "pexels"

    @pytest.mark.asyncio
    async def test_real_key_but_pexels_fails_falls_back_to_mock(self, monkeypatch):
        # Regression test: an invalid/expired key must not leave the UI
        # empty — suggest_brolls() should fall back to the curated mocks.
        monkeypatch.setattr("app.services.broll_service.settings.pexels_api_key", "invalid-or-expired-key")
        with patch("app.services.broll_service.extract_keywords", new_callable=AsyncMock) as mock_kw, \
             patch("app.services.broll_service.search_pexels", new_callable=AsyncMock) as mock_search:
            mock_kw.return_value = ["nature", "business"]
            mock_search.return_value = []  # every Pexels call fails/empties out
            result = await suggest_brolls("un video sobre negocios")
        assert len(result) > 0
        assert all(r.source == "mock" for r in result)

    @pytest.mark.asyncio
    async def test_dedupes_by_id_across_keywords(self, monkeypatch):
        monkeypatch.setattr("app.services.broll_service.settings.pexels_api_key", "fake-key")
        same_result = [BrollSuggestion(
            id="dup", kind="photo", keyword="x",
            thumb_url="http://t", full_url="http://f",
            photographer="Jane", source="pexels",
        )]
        with patch("app.services.broll_service.extract_keywords", new_callable=AsyncMock) as mock_kw, \
             patch("app.services.broll_service.search_pexels", new_callable=AsyncMock) as mock_search:
            mock_kw.return_value = ["nature", "business"]  # 2 keywords, same result each time
            mock_search.return_value = same_result
            result = await suggest_brolls("texto")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_caps_results_at_twelve(self, monkeypatch):
        monkeypatch.setattr("app.services.broll_service.settings.pexels_api_key", "")
        with patch("app.services.broll_service.extract_keywords", new_callable=AsyncMock) as mock_kw:
            mock_kw.return_value = ["nature"]
            result = await suggest_brolls("texto")
        assert len(result) <= 12
