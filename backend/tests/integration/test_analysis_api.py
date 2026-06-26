"""Integration tests for the analysis endpoints."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.ai_service import ANALYSIS_PROMPTS


async def _create_project_with_transcription(client, db_session):
    from app.models.project import Project, Transcription, ProjectStatus, TranscriptionStatus
    project = Project(name="Analysis Test", status=ProjectStatus.COMPLETED)
    db_session.add(project)
    await db_session.flush()
    transcription = Transcription(
        project_id=project.id,
        status=TranscriptionStatus.COMPLETED,
        text="The podcast discussed neural networks and deep learning. "
             "Key topics: transformers, attention mechanisms, and large language models.",
        language_detected="en",
        word_count=22,
    )
    db_session.add(transcription)
    await db_session.commit()
    return project.id


@pytest.mark.asyncio
async def test_get_analysis_types(client):
    resp = await client.get("/api/v1/projects/analysis-types")
    assert resp.status_code == 200
    data = resp.json()
    assert "types" in data
    assert "executive_summary" in data["types"]
    # Compare against the live prompt registry (the actual source of
    # validation in ai_service.analyze_transcript) instead of a hardcoded
    # count, so this doesn't go stale every time a prompt is added/removed.
    assert len(data["types"]) == len(ANALYSIS_PROMPTS)


@pytest.mark.asyncio
async def test_start_analysis_without_transcription(client):
    create = await client.post("/api/v1/projects", json={"name": "No Transcript"})
    pid = create.json()["id"]
    resp = await client.post(
        f"/api/v1/projects/{pid}/analyze",
        json={"analysis_types": ["executive_summary"], "model": "qwen3:8b"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_start_analysis_invalid_type(client, db_session):
    pid = await _create_project_with_transcription(client, db_session)
    resp = await client.post(
        f"/api/v1/projects/{pid}/analyze",
        json={"analysis_types": ["not_a_real_type"], "model": "qwen3:8b"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_start_analysis_background(client, db_session):
    pid = await _create_project_with_transcription(client, db_session)
    # Mock background task to avoid it using the real (non-test) DB session
    with patch("app.routers.analysis._run_analysis_batch") as mock_bg:
        mock_bg.return_value = None
        resp = await client.post(
            f"/api/v1/projects/{pid}/analyze",
            json={"analysis_types": ["executive_summary", "key_ideas"], "model": "qwen3:8b"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "2 type(s)" in data["message"]


@pytest.mark.asyncio
async def test_analyze_single_success(client, db_session):
    pid = await _create_project_with_transcription(client, db_session)
    with patch("app.routers.analysis.ai_service.analyze_transcript", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = ("This is the executive summary.", 1.5)
        resp = await client.post(
            f"/api/v1/projects/{pid}/analyze/single",
            json={"analysis_type": "executive_summary", "model": "qwen3:8b"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "This is the executive summary."
    assert data["model_used"] == "qwen3:8b"


@pytest.mark.asyncio
async def test_analyze_single_invalid_type(client, db_session):
    pid = await _create_project_with_transcription(client, db_session)
    resp = await client.post(
        f"/api/v1/projects/{pid}/analyze/single",
        json={"analysis_type": "bad_type", "model": "qwen3:8b"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_analyze_single_no_transcription(client):
    create = await client.post("/api/v1/projects", json={"name": "Empty"})
    pid = create.json()["id"]
    resp = await client.post(
        f"/api/v1/projects/{pid}/analyze/single",
        json={"analysis_type": "executive_summary", "model": "qwen3:8b"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_analyses_empty(client, db_session):
    pid = await _create_project_with_transcription(client, db_session)
    resp = await client.get(f"/api/v1/projects/{pid}/analyses")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_analyses_after_single(client, db_session):
    pid = await _create_project_with_transcription(client, db_session)
    with patch("app.routers.analysis.ai_service.analyze_transcript", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = ("Summary content.", 0.8)
        await client.post(
            f"/api/v1/projects/{pid}/analyze/single",
            json={"analysis_type": "executive_summary", "model": "qwen3:8b"},
        )
    resp = await client.get(f"/api/v1/projects/{pid}/analyses")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_delete_analysis(client, db_session):
    pid = await _create_project_with_transcription(client, db_session)
    with patch("app.routers.analysis.ai_service.analyze_transcript", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = ("Content", 0.5)
        create = await client.post(
            f"/api/v1/projects/{pid}/analyze/single",
            json={"analysis_type": "conclusions", "model": "qwen3:8b"},
        )
    analysis_id = create.json()["id"]
    delete_resp = await client.delete(f"/api/v1/projects/{pid}/analyses/{analysis_id}")
    assert delete_resp.status_code == 200
    # Verify deleted
    analyses = await client.get(f"/api/v1/projects/{pid}/analyses")
    assert all(a["id"] != analysis_id for a in analyses.json())


@pytest.mark.asyncio
async def test_delete_analysis_not_found(client, db_session):
    pid = await _create_project_with_transcription(client, db_session)
    resp = await client.delete(f"/api/v1/projects/{pid}/analyses/99999")
    assert resp.status_code == 404
