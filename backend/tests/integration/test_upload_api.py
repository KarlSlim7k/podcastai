"""Integration tests for the upload endpoint."""
import pytest
import io
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_upload_valid_file(client, tmp_path):
    create = await client.post("/api/v1/projects", json={"name": "Upload Test"})
    pid = create.json()["id"]

    file_content = b"fake mp3 content" * 100

    # Patch uploads_dir to a temp path so the file actually writes there
    # and patch the background task (which uses real DB)
    from app import config as cfg
    original_uploads = cfg.settings.uploads_dir
    cfg.settings.uploads_dir = tmp_path
    try:
        with patch("app.routers.upload._process_audio_background"):
            resp = await client.post(
                f"/api/v1/projects/{pid}/upload",
                files={"file": ("test.mp3", io.BytesIO(file_content), "audio/mpeg")},
            )
    finally:
        cfg.settings.uploads_dir = original_uploads

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == pid
    assert data["original_filename"] == "test.mp3"


@pytest.mark.asyncio
async def test_upload_invalid_extension(client):
    create = await client.post("/api/v1/projects", json={"name": "Bad Upload"})
    pid = create.json()["id"]

    resp = await client.post(
        f"/api/v1/projects/{pid}/upload",
        files={"file": ("virus.exe", io.BytesIO(b"bad content"), "application/octet-stream")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_to_nonexistent_project(client):
    resp = await client.post(
        "/api/v1/projects/99999/upload",
        files={"file": ("audio.mp3", io.BytesIO(b"content"), "audio/mpeg")},
    )
    assert resp.status_code == 404
