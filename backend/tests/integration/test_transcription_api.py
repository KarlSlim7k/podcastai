"""Integration tests for the transcription endpoints."""
import pytest
import io
from unittest.mock import patch, AsyncMock, MagicMock


async def _create_project(client, db_session, with_transcription=False, with_audio=False):
    from app.models.project import Project, Transcription, ProjectStatus, TranscriptionStatus
    from pathlib import Path

    project = Project(name="Transcription Test", status=ProjectStatus.COMPLETED)
    if with_audio:
        project.audio_file = "/tmp/nonexistent_audio.wav"
    db_session.add(project)
    await db_session.flush()

    if with_transcription:
        t = Transcription(
            project_id=project.id,
            status=TranscriptionStatus.COMPLETED,
            text="Test transcript content.",
            language_detected="en",
            word_count=3,
        )
        db_session.add(t)

    await db_session.commit()
    return project.id


@pytest.mark.asyncio
async def test_start_transcription_no_audio(client):
    create = await client.post("/api/v1/projects", json={"name": "No Audio"})
    pid = create.json()["id"]
    resp = await client.post(
        f"/api/v1/projects/{pid}/transcribe",
        json={"model": "large-v3", "language": "es", "beam_size": 5},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_start_transcription_mocked(client, db_session):
    pid = await _create_project(client, db_session, with_audio=True)
    with patch("app.routers.transcription._run_transcription"), \
         patch("pathlib.Path.exists", return_value=True):
        resp = await client.post(
            f"/api/v1/projects/{pid}/transcribe",
            json={"model": "large-v3", "language": None, "beam_size": 5},
        )
    assert resp.status_code == 200
    assert "Transcription started" in resp.json()["message"]


@pytest.mark.asyncio
async def test_get_transcription_progress(client):
    create = await client.post("/api/v1/projects", json={"name": "Progress Test"})
    pid = create.json()["id"]
    with patch("app.routers.transcription.transcription_service.get_progress",
               return_value={"status": "idle", "progress": 0, "message": "No transcription",
                             "segments_done": 0, "segments_total": 0,
                             "estimated_remaining": None}):
        resp = await client.get(f"/api/v1/projects/{pid}/transcription/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "progress" in data


@pytest.mark.asyncio
async def test_get_transcription_found(client, db_session):
    pid = await _create_project(client, db_session, with_transcription=True)
    db_session.expire_all()
    resp = await client.get(f"/api/v1/projects/{pid}/transcription")
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Test transcript content."


@pytest.mark.asyncio
async def test_get_transcription_not_found(client):
    create = await client.post("/api/v1/projects", json={"name": "Empty"})
    pid = create.json()["id"]
    resp = await client.get(f"/api/v1/projects/{pid}/transcription")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_transcription(client, db_session):
    pid = await _create_project(client, db_session, with_transcription=True)
    db_session.expire_all()
    resp = await client.delete(f"/api/v1/projects/{pid}/transcription")
    assert resp.status_code == 200
    # Verify deleted
    db_session.expire_all()
    get_resp = await client.get(f"/api/v1/projects/{pid}/transcription")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_transcription_not_found(client):
    create = await client.post("/api/v1/projects", json={"name": "Empty"})
    pid = create.json()["id"]
    resp = await client.delete(f"/api/v1/projects/{pid}/transcription")
    assert resp.status_code == 404
