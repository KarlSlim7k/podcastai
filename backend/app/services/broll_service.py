"""AI B-rolls: search contextual stock photos/videos for a clip.

This module:
  1. Uses Ollama to extract 2-4 visual search keywords from a clip's transcript
  2. Searches Pexels (or a mock) for stock photos matching those keywords
  3. Returns a list of suggestions the user can apply as overlays

Design:
  - If ``settings.pexels_api_key`` is set, use the real Pexels API
  - Otherwise, return a small set of placeholder "b-rolls" (curated Pexels
    URLs that always work) so the UI can be developed/tested without a key
  - The b-rolls are NOT auto-applied — the user picks which ones to insert
    and at what timestamps (Phase 11.5)

The search is intentionally simple: extract 2-3 keyword phrases, search
each, return up to 3 results per phrase. The user can preview thumbnails
and pick which ones to use.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import Literal

import httpx

from app.config import settings
from app.services.ai_service import ai_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Types ─────────────────────────────────────────────────────────────────

BrollKind = Literal["photo", "video"]


@dataclass
class BrollSuggestion:
    """One stock image/video that could be overlaid on the clip.

    Attributes:
        id: Pexels ID (or a stable mock id like "mock-1").
        kind: ``"photo"`` or ``"video"``.
        keyword: The search phrase that produced this result.
        thumb_url: Small preview image (always available, fast to load).
        full_url: Full-resolution image (or video) URL.
        photographer: Credit string ("John Doe on Pexels").
        source: ``"pexels"`` or ``"mock"``.
        duration_s: For videos, the clip duration. For photos, 0.
    """

    id: str
    kind: BrollKind
    keyword: str
    thumb_url: str
    full_url: str
    photographer: str
    source: str
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ── Curated mock data (always available, no API key needed) ──────────────
# These are real, public Pexels photo URLs that are stable. We use a small
# set so the UI can be developed without a Pexels account. Photos are
# nature/business/technology themed so they're broadly applicable.

_MOCK_BROLLS: list[BrollSuggestion] = [
    BrollSuggestion(
        id="mock-1", kind="photo", keyword="nature",
        thumb_url="https://images.pexels.com/photos/2387873/pexels-photo-2387873.jpeg?w=400",
        full_url="https://images.pexels.com/photos/2387873/pexels-photo-2387873.jpeg?w=1920",
        photographer="Pixabay on Pexels", source="mock",
    ),
    BrollSuggestion(
        id="mock-2", kind="photo", keyword="city",
        thumb_url="https://images.pexels.com/photos/466685/pexels-photo-466685.jpeg?w=400",
        full_url="https://images.pexels.com/photos/466685/pexels-photo-466685.jpeg?w=1920",
        photographer="Pixabay on Pexels", source="mock",
    ),
    BrollSuggestion(
        id="mock-3", kind="photo", keyword="technology",
        thumb_url="https://images.pexels.com/photos/356056/pexels-photo-356056.jpeg?w=400",
        full_url="https://images.pexels.com/photos/356056/pexels-photo-356056.jpeg?w=1920",
        photographer="Pixabay on Pexels", source="mock",
    ),
    BrollSuggestion(
        id="mock-4", kind="photo", keyword="business",
        thumb_url="https://images.pexels.com/photos/3184435/pexels-photo-3184435.jpeg?w=400",
        full_url="https://images.pexels.com/photos/3184435/pexels-photo-3184435.jpeg?w=1920",
        photographer=" fauxels on Pexels", source="mock",
    ),
    BrollSuggestion(
        id="mock-5", kind="photo", keyword="people",
        thumb_url="https://images.pexels.com/photos/3184291/pexels-photo-3184291.jpeg?w=400",
        full_url="https://images.pexels.com/photos/3184291/pexels-photo-3184291.jpeg?w=1920",
        photographer=" fauxels on Pexels", source="mock",
    ),
    BrollSuggestion(
        id="mock-6", kind="photo", keyword="work",
        thumb_url="https://images.pexels.com/photos/3183150/pexels-photo-3183150.jpeg?w=400",
        full_url="https://images.pexels.com/photos/3183150/pexels-photo-3183150.jpeg?w=1920",
        photographer=" fauxels on Pexels", source="mock",
    ),
    BrollSuggestion(
        id="mock-7", kind="photo", keyword="food",
        thumb_url="https://images.pexels.com/photos/1640777/pexels-photo-1640777.jpeg?w=400",
        full_url="https://images.pexels.com/photos/1640777/pexels-photo-1640777.jpeg?w=1920",
        photographer="Kaboompics on Pexels", source="mock",
    ),
    BrollSuggestion(
        id="mock-8", kind="photo", keyword="travel",
        thumb_url="https://images.pexels.com/photos/1271619/pexels-photo-1271619.jpeg?w=400",
        full_url="https://images.pexels.com/photos/1271619/pexels-photo-1271619.jpeg?w=1920",
        photographer="Pixabay on Pexels", source="mock",
    ),
    BrollSuggestion(
        id="mock-9", kind="photo", keyword="fitness",
        thumb_url="https://images.pexels.com/photos/841130/pexels-photo-841130.jpeg?w=400",
        full_url="https://images.pexels.com/photos/841130/pexels-photo-841130.jpeg?w=1920",
        photographer="Pixabay on Pexels", source="mock",
    ),
    BrollSuggestion(
        id="mock-10", kind="photo", keyword="abstract",
        thumb_url="https://images.pexels.com/photos/1762851/pexels-photo-1762851.jpeg?w=400",
        full_url="https://images.pexels.com/photos/1762851/pexels-photo-1762851.jpeg?w=1920",
        photographer="Pixabay on Pexels", source="mock",
    ),
    BrollSuggestion(
        id="mock-11", kind="photo", keyword="motivation",
        thumb_url="https://images.pexels.com/photos/2747449/pexels-photo-2747449.jpeg?w=400",
        full_url="https://images.pexels.com/photos/2747449/pexels-photo-2747449.jpeg?w=1920",
        photographer="Pixabay on Pexels", source="mock",
    ),
    BrollSuggestion(
        id="mock-12", kind="photo", keyword="success",
        thumb_url="https://images.pexels.com/photos/210607/pexels-photo-210607.jpeg?w=400",
        full_url="https://images.pexels.com/photos/210607/pexels-photo-210607.jpeg?w=1920",
        photographer="Pixabay on Pexels", source="mock",
    ),
]


# ── Ollama keyword extraction ─────────────────────────────────────────────

_KEYWORDS_PROMPT = """Analiza este fragmento de transcripción de un podcast/video y extrae 2-4 palabras clave visuales (en inglés) para buscar imágenes de stock que ilustren lo que se está hablando.

CRITERIOS:
- Palabras en inglés (Pexels funciona mejor en inglés)
- Cosas VISUALES concretas: objetos, lugares, acciones, conceptos abstractos populares
- Evita palabras abstractas tipo "filosofía" o "estrategia" — busca equivalentes visuales ("chess board", "mountain summit")
- Si no hay nada visual, devuelve ["abstract", "business"]
- Responde SOLO un JSON array de strings, nada más

TRANSCRIPCIÓN:
---
{transcript}
---

JSON:"""


async def extract_keywords(transcript: str) -> list[str]:
    """Use Ollama to extract 2-4 visual search keywords from a transcript.

    Falls back to ["abstract", "business"] if Ollama is unavailable.
    """
    prompt = _KEYWORDS_PROMPT.format(transcript=(transcript or "")[:2000])
    try:
        raw = await ai_service.generate(
            prompt, model=settings.ollama_default_model,
            system="You extract visual keywords. Reply only with a JSON array."
        )
        # Try to parse a JSON array
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            if isinstance(data, list) and all(isinstance(k, str) for k in data):
                keywords = [k.strip().lower() for k in data if k.strip()][:4]
                if keywords:
                    logger.info("broll_keywords_extracted", keywords=keywords)
                    return keywords
    except Exception as e:
        logger.warning("broll_keyword_extraction_failed", error=str(e))
    # Fallback
    return ["abstract", "business"]


# ── Pexels API ────────────────────────────────────────────────────────────

async def search_pexels(query: str, per_page: int = 3) -> list[BrollSuggestion]:
    """Search Pexels for photos matching a query.

    Returns an empty list if:
      - No API key configured
      - Pexels returns an error
      - No results
    """
    api_key = getattr(settings, "pexels_api_key", None)
    if not api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": per_page, "orientation": "portrait"},
                headers={"Authorization": api_key},
            )
            if r.status_code != 200:
                logger.warning("pexels_api_error", status=r.status_code, query=query)
                return []
            data = r.json()
            results: list[BrollSuggestion] = []
            for photo in data.get("photos", []):
                src = photo.get("src", {})
                results.append(BrollSuggestion(
                    id=str(photo.get("id", "")),
                    kind="photo",
                    keyword=query,
                    thumb_url=src.get("tiny", ""),
                    full_url=src.get("original", src.get("large2x", "")),
                    photographer=photo.get("photographer", "Unknown"),
                    source="pexels",
                ))
            return results
    except Exception as e:
        logger.warning("pexels_search_failed", error=str(e), query=query)
        return []


def _filter_mock_brolls(keyword: str) -> list[BrollSuggestion]:
    """Return mock b-rolls whose keyword is a prefix/substring of ``keyword``.

    If no keyword matches, return a few generic ones so the UI is never empty.
    """
    keyword_lower = keyword.lower().strip()
    matches = [b for b in _MOCK_BROLLS if keyword_lower in b.keyword or b.keyword in keyword_lower]
    if not matches:
        # Return 3 generic ones for variety
        return _MOCK_BROLLS[:3]
    return matches[:3]


# ── Public API ────────────────────────────────────────────────────────────

async def suggest_brolls(
    transcript: str,
    *,
    per_keyword: int = 3,
) -> list[BrollSuggestion]:
    """End-to-end: extract keywords + search Pexels (or mock) + dedupe.

    Returns a list of up to 12 unique suggestions. If Pexels is not
    configured, the mock is used as a fallback so the UI is never empty.
    """
    keywords = await extract_keywords(transcript)
    logger.info("broll_search_start", keywords=keywords, has_pexels=bool(getattr(settings, "pexels_api_key", None)))

    all_results: list[BrollSuggestion] = []
    seen_ids: set[str] = set()

    # Try Pexels for each keyword first
    use_pexels = bool(getattr(settings, "pexels_api_key", None))
    if use_pexels:
        for kw in keywords:
            results = await search_pexels(kw, per_page=per_keyword)
            for r in results:
                if r.id not in seen_ids:
                    seen_ids.add(r.id)
                    all_results.append(r)

    # Mock fallback: used when no key is configured, OR when a key is
    # configured but every Pexels call failed/returned nothing (e.g. an
    # invalid or expired key) — the UI should never be left empty.
    if not all_results:
        for kw in keywords:
            mocks = _filter_mock_brolls(kw)
            for m in mocks:
                if m.id not in seen_ids:
                    seen_ids.add(m.id)
                    all_results.append(m)
        # Pad with generics so the UI always has at least 6 cards
        for m in _MOCK_BROLLS:
            if m.id not in seen_ids:
                seen_ids.add(m.id)
                all_results.append(m)
            if len(all_results) >= 12:
                break

    logger.info("broll_search_done", results=len(all_results))
    return all_results[:12]


def brolls_to_json(suggestions: list[BrollSuggestion]) -> str:
    """Serialize a list of suggestions to JSON."""
    return json.dumps([s.to_dict() for s in suggestions])
