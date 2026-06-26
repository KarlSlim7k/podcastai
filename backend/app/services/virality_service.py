"""AI Virality Score — predict how viral a clip is likely to be.

Uses Ollama to analyze a clip's transcript + metadata and produce a
0-100 score plus a 3-dimension breakdown (hook strength, pacing,
emotional pull) and a one-sentence reason.

The score is intentionally simple to explain to the user:
  - 0-39  : low virality (informational, niche, slow build)
  - 40-69 : medium virality (interesting, worth posting)
  - 70-100: high virality (strong hook, emotion, shareable)

The service is forgiving: if Ollama is offline, the score falls back
to a "pending" state on the clip (so the UI doesn't break) and the
job retries next time the user asks for it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import Any

from app.services.ai_service import ai_service
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ── Result shape ───────────────────────────────────────────────────────────

@dataclass
class ViralityBreakdown:
    """Detailed virality analysis, persisted as JSON in ``clips.virality_breakdown``."""

    hook: int        # 1-5 — strength of the opening line / first 3 seconds
    pacing: int      # 1-5 — tempo, sentence rhythm, dynamism
    emotional_pull: int  # 1-5 — emotional resonance, shareability
    shareability: int    # 1-5 — would someone send this to a friend?

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ViralityResult:
    """The full virality output for one clip."""

    score: int                 # 0-100, overall
    reason: str                # 1-sentence TL;DR
    breakdown: ViralityBreakdown
    category: str              # funny | insightful | controversial | emotional | informative
    model_used: str            # which Ollama model produced this

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "reason": self.reason,
            "breakdown": self.breakdown.to_dict(),
            "category": self.category,
            "model_used": self.model_used,
        }


# ── Prompt ─────────────────────────────────────────────────────────────────

# The prompt is bilingual-friendly: Ollama is good at returning strict JSON
# when you (a) tell it what schema you want, (b) show an example, and
# (c) remind it to ONLY return JSON (no preamble).

_SYSTEM = """You are a viral content analyst who has studied 10,000+ TikTok / Reels / Shorts.
You rate clips on a 0-100 "virality score" based on:
  1. **Hook** (first 3 seconds) — does it grab attention? is it a question, bold claim, surprise?
  2. **Pacing** — sentence rhythm, dynamism, no slow build
  3. **Emotional pull** — does it make you feel something? (humor, awe, outrage, warmth)
  4. **Shareability** — would someone send this to a friend?

You ALWAYS reply with strict JSON, no preamble, no markdown fences."""

_PROMPT = """Analiza este clip de podcast y devuelve SOLO un JSON con este schema exacto:

{{
  "score": <int 0-100>,
  "hook": <int 1-5>,
  "pacing": <int 1-5>,
  "emotional_pull": <int 1-5>,
  "shareability": <int 1-5>,
  "category": "<uno de: funny | insightful | controversial | emotional | informative>",
  "reason": "<1 frase corta, máx 120 chars, en español, explicando el score>"
}}

CRITERIOS:
- 80-100: hook irresistible, alta emoción, shareable. Ej: "I quit my 6-figure job..."
- 60-79: interesante, hook decente, vale la pena publicar
- 40-59: correcto pero genérico, sin gancho fuerte
- 0-39: informativo lento, nicho, no compite por atención

TÍTULO: {title}
DESCRIPCIÓN: {description}
DURACIÓN: {duration:.1f} segundos
TRANSCRIPCIÓN:
---
{transcript}
---

Responde SOLO el JSON, sin texto antes ni después."""


# ── Public API ─────────────────────────────────────────────────────────────

async def compute_virality(
    title: str,
    description: str | None,
    transcript: str,
    duration: float,
    model: str | None = None,
) -> ViralityResult:
    """Compute a virality score for a clip.

    Args:
        title: The clip title (set when the clip was created).
        description: Optional longer description.
        transcript: The clip's transcript excerpt (15-90s of speech).
        duration: Length of the clip in seconds.
        model: Ollama model name. Defaults to ``settings.ollama_default_model``.

    Returns:
        A :class:`ViralityResult` with the score, breakdown, and reason.

    Raises:
        RuntimeError: if Ollama returns an unparseable response after one retry.
    """
    model = model or settings.ollama_default_model
    prompt = _PROMPT.format(
        title=title or "(sin título)",
        description=description or "(sin descripción)",
        duration=duration,
        transcript=(transcript or "(sin transcripción)")[:3500],  # cap for prompt size
    )

    # First attempt
    try:
        raw = await ai_service.generate(prompt, model=model, system=_SYSTEM)
        result = _parse_response(raw, model)
        if result:
            logger.info("virality_computed", score=result.score, model=model)
            return result
    except Exception as e:
        logger.warning("virality_first_attempt_failed", error=str(e))

    # Retry once with a stricter prompt (some small models need the reminder)
    try:
        strict_prompt = prompt + "\n\nIMPORTANT: Return ONLY the JSON object, nothing else."
        raw = await ai_service.generate(strict_prompt, model=model, system=_SYSTEM)
        result = _parse_response(raw, model)
        if result:
            logger.info("virality_computed_retry", score=result.score, model=model)
            return result
    except Exception as e:
        logger.error("virality_retry_failed", error=str(e))

    raise RuntimeError("Could not parse virality score from Ollama response")


# ── Response parser ────────────────────────────────────────────────────────

# Some Ollama models wrap JSON in ```json ... ``` fences. We strip those.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _parse_response(raw: str, model: str) -> ViralityResult | None:
    """Extract a ViralityResult from the model's raw output.

    Returns None if the response cannot be parsed (so the caller can retry).
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()

    # Strip code fences if present
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    # Some models add a preamble like "Here is the JSON:". Try to find the
    # first ``{`` and last ``}`` and parse just that slice.
    if not text.startswith("{"):
        i = text.find("{")
        j = text.rfind("}")
        if i >= 0 and j > i:
            text = text[i : j + 1]

    try:
        data: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("virality_json_parse_failed", raw=raw[:200])
        return None

    try:
        score = _clamp_int(data.get("score"), 0, 100)
        breakdown = ViralityBreakdown(
            hook=_clamp_int(data.get("hook"), 1, 5),
            pacing=_clamp_int(data.get("pacing"), 1, 5),
            emotional_pull=_clamp_int(data.get("emotional_pull"), 1, 5),
            shareability=_clamp_int(data.get("shareability"), 1, 5),
        )
        reason = (data.get("reason") or "").strip()[:500]
        category = (data.get("category") or "informative").strip().lower()
        # Whitelist category so we never store garbage
        if category not in {"funny", "insightful", "controversial", "emotional", "informative"}:
            category = "informative"

        return ViralityResult(
            score=score,
            reason=reason,
            breakdown=breakdown,
            category=category,
            model_used=model,
        )
    except (TypeError, ValueError) as e:
        logger.warning("virality_field_parse_failed", error=str(e), data=list(data.keys()))
        return None


def _clamp_int(value: Any, lo: int, hi: int) -> int:
    """Coerce a value to an int and clamp it to [lo, hi]."""
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


# ── Singleton-style accessor ───────────────────────────────────────────────
# We don't need a class instance — the module functions are stateless.
# Tests can call them directly.

virality_service = compute_virality  # alias for symmetry with other services
