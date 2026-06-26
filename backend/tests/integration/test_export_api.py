"""Integration tests for the export endpoints."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


async def _create_project_with_transcription(client, db_session):
    from app.models.project import Project, Transcription, ProjectStatus, TranscriptionStatus
    project = Project(name="Export Test", status=ProjectStatus.COMPLETED)
    db_session.add(project)
    await db_session.flush()
    transcription = Transcription(
        project_id=project.id,
        status=TranscriptionStatus.COMPLETED,
        text="This is the transcript content for export testing.",
        language_detected="en",
        word_count=9,
    )
    db_session.add(transcription)
    await db_session.commit()
    return project.id


def _make_export_mock(tmp_path: Path, filename: str = "export.txt") -> Path:
    p = tmp_path / filename
    p.write_text("Export content here.")
    return p


@pytest.mark.asyncio
async def test_create_txt_export(client, db_session, tmp_path):
    pid = await _create_project_with_transcription(client, db_session)
    fake_path = _make_export_mock(tmp_path, "export.txt")
    with patch("app.routers.export.export_service.export_txt", return_value=fake_path):
        resp = await client.post(
            f"/api/v1/projects/{pid}/export",
            json={"format": "txt"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["export_type"] == "txt"
    assert data["file_size"] > 0


@pytest.mark.asyncio
async def test_create_markdown_export(client, db_session, tmp_path):
    pid = await _create_project_with_transcription(client, db_session)
    fake_path = _make_export_mock(tmp_path, "export.md")
    with patch("app.routers.export.export_service.export_markdown", return_value=fake_path):
        resp = await client.post(
            f"/api/v1/projects/{pid}/export",
            json={"format": "markdown"},
        )
    assert resp.status_code == 200
    assert resp.json()["export_type"] == "markdown"


@pytest.mark.asyncio
async def test_create_json_export(client, db_session, tmp_path):
    pid = await _create_project_with_transcription(client, db_session)
    fake_path = _make_export_mock(tmp_path, "export.json")
    with patch("app.routers.export.export_service.export_json", return_value=fake_path):
        resp = await client.post(
            f"/api/v1/projects/{pid}/export",
            json={"format": "json"},
        )
    assert resp.status_code == 200
    assert resp.json()["export_type"] == "json"


@pytest.mark.asyncio
async def test_export_without_transcription_fails(client):
    create = await client.post("/api/v1/projects", json={"name": "Empty"})
    pid = create.json()["id"]
    resp = await client.post(f"/api/v1/projects/{pid}/export", json={"format": "txt"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_exports_empty(client, db_session):
    pid = await _create_project_with_transcription(client, db_session)
    resp = await client.get(f"/api/v1/projects/{pid}/exports")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_exports_after_create(client, db_session, tmp_path):
    pid = await _create_project_with_transcription(client, db_session)
    fake_path = _make_export_mock(tmp_path)
    with patch("app.routers.export.export_service.export_txt", return_value=fake_path):
        create_resp = await client.post(f"/api/v1/projects/{pid}/export", json={"format": "txt"})
    assert create_resp.status_code == 200
    # Expire all objects in session so the next query fetches fresh data
    db_session.expire_all()
    resp = await client.get(f"/api/v1/projects/{pid}/exports")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_download_export(client, db_session, tmp_path):
    pid = await _create_project_with_transcription(client, db_session)
    fake_path = _make_export_mock(tmp_path, "out.txt")
    with patch("app.routers.export.export_service.export_txt", return_value=fake_path):
        create_resp = await client.post(
            f"/api/v1/projects/{pid}/export",
            json={"format": "txt"},
        )
    export_id = create_resp.json()["id"]
    dl = await client.get(f"/api/v1/projects/{pid}/export/{export_id}/download")
    assert dl.status_code == 200


@pytest.mark.asyncio
async def test_download_export_not_found(client, db_session):
    pid = await _create_project_with_transcription(client, db_session)
    resp = await client.get(f"/api/v1/projects/{pid}/export/99999/download")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_service_exception_returns_500(client, db_session):
    pid = await _create_project_with_transcription(client, db_session)
    with patch("app.routers.export.export_service.export_txt", side_effect=RuntimeError("Disk full")):
        resp = await client.post(f"/api/v1/projects/{pid}/export", json={"format": "txt"})
    assert resp.status_code == 500
