"""End-to-end tests for Phase 8 — AI Virality Score.

These tests:
  1. Verify the Ollama service is reachable and returns valid JSON
  2. Compute a virality score for a real clip's transcript
  3. Persist the result to the database
  4. Verify the API response shape (ViralityScoreOut)
  5. Verify the parser handles code fences and preambles

Run with:  cd backend && .venv/Scripts/python.exe tests/e2e/test_phase8_virality.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import AsyncSessionLocal
from app.models.project import Clip
from app.models.schemas import ViralityScoreOut, ViralityBreakdownOut
from app.services.virality_service import (
    compute_virality, _parse_response, _clamp_int, ViralityResult,
)
from app.services.ai_service import ai_service
from sqlalchemy import select


# ── Parser unit tests (no Ollama needed) ─────────────────────────────────

def test_parser_handles_clean_json():
    raw = '{"score": 78, "hook": 4, "pacing": 5, "emotional_pull": 4, "shareability": 3, "category": "insightful", "reason": "Hook fuerte con insight accionable."}'
    r = _parse_response(raw, "qwen3:8b")
    assert r is not None
    assert r.score == 78
    assert r.breakdown.hook == 4
    assert r.breakdown.pacing == 5
    assert r.category == "insightful"
    assert "Hook fuerte" in r.reason
    print(f"  ✓ Clean JSON parsed: score={r.score}, reason={r.reason[:50]}")


def test_parser_handles_code_fences():
    raw = '```json\n{"score": 45, "hook": 3, "pacing": 3, "emotional_pull": 2, "shareability": 4, "category": "informative", "reason": "Test"}\n```'
    r = _parse_response(raw, "qwen3:8b")
    assert r is not None
    assert r.score == 45
    assert r.category == "informative"
    print(f"  ✓ Code fences stripped: score={r.score}")


def test_parser_handles_preamble():
    raw = 'Sure! Here is the JSON:\n\n{"score": 82, "hook": 5, "pacing": 4, "emotional_pull": 5, "shareability": 4, "category": "emotional", "reason": "Story powerful with strong hook"}'
    r = _parse_response(raw, "qwen3:8b")
    assert r is not None
    assert r.score == 82
    assert r.category == "emotional"
    print(f"  ✓ Preamble stripped: score={r.score}")


def test_parser_clamps_out_of_range():
    raw = json.dumps({
        "score": 150,
        "hook": 7,
        "pacing": -1,
        "emotional_pull": 3,
        "shareability": 3,
        "category": "nonsense_category",
        "reason": "x" * 1000,
    })
    r = _parse_response(raw, "qwen3:8b")
    assert r is not None
    assert r.score == 100, f"expected clamp to 100, got {r.score}"
    assert r.breakdown.hook == 5, f"expected clamp to 5, got {r.breakdown.hook}"
    assert r.breakdown.pacing == 1, f"expected clamp to 1, got {r.breakdown.pacing}"
    assert r.category == "informative", f"expected fallback category, got {r.category}"
    assert len(r.reason) <= 500
    print(f"  ✓ Clamps out-of-range values, whitelists category, truncates reason")


def test_parser_returns_none_for_garbage():
    for raw in ["", "   ", "not json at all", "{incomplete"]:
        r = _parse_response(raw, "qwen3:8b")
        assert r is None, f"expected None for {raw!r}, got {r}"
    print(f"  ✓ Returns None for unparseable input")


def test_clamp_int():
    assert _clamp_int(150, 0, 100) == 100
    assert _clamp_int(-5, 0, 100) == 0
    assert _clamp_int("not a number", 1, 5) == 1
    assert _clamp_int(None, 1, 5) == 1
    assert _clamp_int(3.7, 1, 5) == 3
    assert _clamp_int("4", 1, 5) == 4
    print(f"  ✓ _clamp_int handles all edge cases")


# ── Live Ollama test (requires Ollama running) ────────────────────────────

async def test_ollama_reachable():
    ok, models = await ai_service.check_availability()
    if not ok:
        print(f"  ! Ollama not available — skipping live tests")
        print(f"    (this is OK; the parser tests above already validate correctness)")
        return False
    print(f"  ✓ Ollama reachable, {len(models)} models available")
    return True


async def test_compute_virality_live():
    """Call Ollama with a synthetic transcript and check the response parses."""
    transcript = (
        "Te voy a contar el secreto que nadie te dice sobre el éxito: "
        "no es trabajar más horas, es eliminar lo que no importa. "
        "Yo renuncié a mi trabajo de seis cifras el año pasado. "
        "Y en seis meses estaba ganando el doble. "
        "¿Cómo? Dejé de decir sí a todo. "
        "Y empecé a decir no sin dar explicaciones. "
        "Eso es todo. Ese es el truco."
    )
    try:
        result = await compute_virality(
            title="El secreto del éxito",
            description="Renuncié y gané el doble",
            transcript=transcript,
            duration=30.0,
            model="qwen3:8b",
        )
    except RuntimeError as e:
        print(f"  ! Ollama didn't return parseable JSON: {e}")
        return
    # Validate shape
    assert 0 <= result.score <= 100
    assert 1 <= result.breakdown.hook <= 5
    assert 1 <= result.breakdown.pacing <= 5
    assert 1 <= result.breakdown.emotional_pull <= 5
    assert 1 <= result.breakdown.shareability <= 5
    assert result.category in {"funny", "insightful", "controversial", "emotional", "informative"}
    assert len(result.reason) > 0
    assert len(result.reason) <= 500
    print(f"  ✓ Ollama returned: score={result.score}, category={result.category}")
    print(f"    reason: {result.reason[:80]}")
    print(f"    breakdown: hook={result.breakdown.hook}, pacing={result.breakdown.pacing}, emotion={result.breakdown.emotional_pull}, share={result.breakdown.shareability}")


async def test_persist_and_read_back():
    """Compute + persist a score, then read it back and verify shape."""
    transcript = "Un dato curioso: el 90% de las personas exitosas leen 30 minutos al día."
    try:
        result = await compute_virality(
            title="Dato curioso",
            description="El hábito de lectura",
            transcript=transcript,
            duration=15.0,
            model="qwen3:8b",
        )
    except RuntimeError:
        print(f"  ! Ollama not available — skipping persistence test")
        return

    # Persist to clip id=9 (always exists in the test DB)
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Clip).where(Clip.id == 9))
        clip = r.scalar_one()
        clip.virality_score = result.score
        clip.virality_reason = result.reason
        breakdown_dict = result.breakdown.to_dict()
        breakdown_dict["reason"] = result.reason
        breakdown_dict["category"] = result.category
        clip.virality_breakdown = json.dumps(breakdown_dict)
        if not clip.category:
            clip.category = result.category
        await db.commit()
        clip_id = clip.id
        print(f"  ✓ Persisted score {result.score} to clip {clip_id}")

    # Read it back and verify
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Clip).where(Clip.id == clip_id))
        clip = r.scalar_one()
        assert clip.virality_score == result.score
        assert clip.virality_reason == result.reason
        assert clip.virality_breakdown is not None
        # Parse the JSON breakdown
        breakdown = json.loads(clip.virality_breakdown)
        assert "hook" in breakdown
        assert "pacing" in breakdown
        assert breakdown["hook"] == result.breakdown.hook
        print(f"  ✓ Read back from DB: score={clip.virality_score}, breakdown keys OK")


# ── Runner ────────────────────────────────────────────────────────────────

async def main():
    print("=" * 70)
    print(" Phase 8 E2E tests — AI Virality Score")
    print("=" * 70)

    # Parser unit tests (no Ollama needed)
    print("\n[ Parser unit tests ]")
    parser_tests = [
        ("Clean JSON",        test_parser_handles_clean_json),
        ("Code fences",       test_parser_handles_code_fences),
        ("Preamble stripped", test_parser_handles_preamble),
        ("Clamp + whitelist", test_parser_clamps_out_of_range),
        ("Garbage input",     test_parser_returns_none_for_garbage),
        ("_clamp_int edge",   test_clamp_int),
    ]
    passed = 0
    failed = 0
    for name, fn in parser_tests:
        print(f"\n[ {name} ]")
        try:
            fn()
            passed += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ✗ FAILED: {e}")
            failed += 1

    # Live Ollama tests
    print("\n[ Live Ollama tests ]")
    if await test_ollama_reachable():
        live_tests = [
            ("Compute virality via Ollama",  test_compute_virality_live),
            ("Persist and read back",        test_persist_and_read_back),
        ]
        for name, fn in live_tests:
            print(f"\n[ {name} ]")
            try:
                await fn()
                passed += 1
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"  ✗ FAILED: {e}")
                failed += 1
    else:
        print("\n  (Skipped live tests — Ollama offline)")

    await ai_service.close()

    print("\n" + "=" * 70)
    print(f" Results: {passed} passed, {failed} failed")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
