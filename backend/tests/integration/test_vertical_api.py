"""Integration tests for the vertical editor endpoints (app/routers/vertical.py).

``render_vertical()`` / the background render task are always mocked here —
no real ffmpeg invocation. See ``tests/qa_vertical_editor_matrix.py`` for an
end-to-end check against real ffmpeg.
"""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.project import Clip, Project, Transcription, VerticalPreset, VerticalRender, VerticalRenderStatus


async def _create_project_with_clip(db_session, tmp_path, with_audio=True, with_transcription=True):
    project = Project(name="Vertical Test")
    db_session.add(project)
    await db_session.flush()

    if with_transcription:
        transcription = Transcription(
            project_id=project.id,
            text="hola mundo de prueba",
            segments=[{
                "start": 0.0, "end": 5.0, "text": "hola mundo de prueba",
                "words": [
                    {"start": 0.0, "end": 0.4, "word": "hola"},
                    {"start": 0.4, "end": 0.8, "word": "mundo"},
                ],
            }],
        )
        db_session.add(transcription)
        await db_session.flush()
        transcription_id = transcription.id
    else:
        # Clip still needs a (possibly orphan) transcription_id FK value.
        transcription = Transcription(project_id=project.id, text="x", segments=None)
        db_session.add(transcription)
        await db_session.flush()
        transcription_id = transcription.id

    audio_path = None
    if with_audio:
        audio_path = tmp_path / "clip_audio.wav"
        audio_path.write_bytes(b"fake-audio-bytes")

    clip = Clip(
        transcription_id=transcription_id,
        project_id=project.id,
        start=0.0, end=5.0, duration=5.0,
        title="Clip de prueba",
        audio_clip_path=str(audio_path) if audio_path else None,
        video_clip_path=str(audio_path) if audio_path else None,
    )
    db_session.add(clip)
    await db_session.commit()
    return project.id, clip.id


# ── /vertical/styles ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_vertical_styles(client):
    resp = await client.get("/api/v1/vertical/styles")
    assert resp.status_code == 200
    data = resp.json()
    assert {s["id"] for s in data["layouts"]} >= {"split", "centered", "fill", "auto"}
    assert {s["id"] for s in data["backgrounds"]} >= {"blur", "solid", "gradient", "zoom"}
    assert {s["id"] for s in data["subtitle_styles"]} >= {"standard", "karaoke", "neon", "mrbeast", "hormozi", "tiktok_classic"}


# ── Presets CRUD ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_get_preset(client):
    resp = await client.post("/api/v1/vertical/presets", json={"name": "Mi preset", "layout": "centered"})
    assert resp.status_code == 200
    preset_id = resp.json()["id"]
    assert resp.json()["layout"] == "centered"

    get_resp = await client.get(f"/api/v1/vertical/presets/{preset_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Mi preset"


@pytest.mark.asyncio
async def test_create_preset_duplicate_name_conflicts(client):
    await client.post("/api/v1/vertical/presets", json={"name": "Duplicado"})
    resp = await client.post("/api/v1/vertical/presets", json={"name": "Duplicado"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_preset_not_found(client):
    resp = await client.get("/api/v1/vertical/presets/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_presets_includes_created(client):
    await client.post("/api/v1/vertical/presets", json={"name": "Listable"})
    resp = await client.get("/api/v1/vertical/presets")
    assert resp.status_code == 200
    assert any(p["name"] == "Listable" for p in resp.json()["presets"])


@pytest.mark.asyncio
async def test_update_preset(client):
    create = await client.post("/api/v1/vertical/presets", json={"name": "Editable", "layout": "fill"})
    preset_id = create.json()["id"]
    resp = await client.put(
        f"/api/v1/vertical/presets/{preset_id}",
        json={"name": "Editable", "layout": "split"},
    )
    assert resp.status_code == 200
    assert resp.json()["layout"] == "split"


@pytest.mark.asyncio
async def test_update_preset_not_found(client):
    resp = await client.put("/api/v1/vertical/presets/99999", json={"name": "x"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_preset(client):
    create = await client.post("/api/v1/vertical/presets", json={"name": "Borrable"})
    preset_id = create.json()["id"]
    resp = await client.delete(f"/api/v1/vertical/presets/{preset_id}")
    assert resp.status_code == 200
    assert (await client.get(f"/api/v1/vertical/presets/{preset_id}")).status_code == 404


@pytest.mark.asyncio
async def test_delete_preset_not_found(client):
    resp = await client.delete("/api/v1/vertical/presets/99999")
    assert resp.status_code == 404


# ── Create render ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_render_clip_not_found(client, db_session, tmp_path):
    pid, _ = await _create_project_with_clip(db_session, tmp_path)
    resp = await client.post(f"/api/v1/projects/{pid}/clips/99999/vertical", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_render_no_audio_extracted(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path, with_audio=False)
    resp = await client.post(f"/api/v1/projects/{pid}/clips/{cid}/vertical", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_render_success_persists_pending_row(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path)
    with patch("app.routers.vertical._do_render_vertical", new_callable=AsyncMock) as mock_task:
        resp = await client.post(
            f"/api/v1/projects/{pid}/clips/{cid}/vertical",
            json={"layout": "split", "bg_style": "blur", "sub_style": "karaoke"},
        )
    assert resp.status_code == 200
    mock_task.assert_called_once()

    list_resp = await client.get(f"/api/v1/projects/{pid}/vertical")
    renders = list_resp.json()["renders"]
    assert len(renders) == 1
    assert renders[0]["status"] == VerticalRenderStatus.PENDING.value
    assert renders[0]["layout"] == "split"


@pytest.mark.asyncio
async def test_create_render_invalid_layout_rejected(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path)
    resp = await client.post(
        f"/api/v1/projects/{pid}/clips/{cid}/vertical",
        json={"layout": "not-a-real-layout"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_render_with_broll_placements(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path)
    with patch("app.routers.vertical._do_render_vertical", new_callable=AsyncMock):
        resp = await client.post(
            f"/api/v1/projects/{pid}/clips/{cid}/vertical",
            json={"broll_placements": [{"url": "http://x/img.jpg", "start": 0.0, "end": 1.0}]},
        )
    assert resp.status_code == 200


# ── Batch render ────────────────────────────────────────────────────────────────

async def _add_clip_to_project(db_session, project, tmp_path, with_audio=True):
    """Add a second clip to an already-created project (same transcription)."""
    audio_path = None
    if with_audio:
        audio_path = tmp_path / "clip_audio_2.wav"
        audio_path.write_bytes(b"fake-audio-bytes")
    clip = Clip(
        transcription_id=project.transcription.id,
        project_id=project.id,
        start=0.0, end=5.0, duration=5.0,
        title="Segundo clip",
        audio_clip_path=str(audio_path) if audio_path else None,
        video_clip_path=str(audio_path) if audio_path else None,
    )
    db_session.add(clip)
    await db_session.commit()
    return clip.id


@pytest.mark.asyncio
async def test_batch_render_creates_one_row_per_clip(client, db_session, tmp_path):
    pid, cid1 = await _create_project_with_clip(db_session, tmp_path)
    project = (await db_session.execute(
        select(Project).where(Project.id == pid).options(selectinload(Project.transcription))
    )).scalar_one()
    cid2 = await _add_clip_to_project(db_session, project, tmp_path)
    with patch("app.routers.vertical._do_render_vertical", new_callable=AsyncMock) as mock_task:
        resp = await client.post(
            f"/api/v1/projects/{pid}/vertical/batch",
            json={"clip_ids": [cid1, cid2], "request": {"layout": "fill"}},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["render_ids"]) == 2
    assert data["errors"] == []
    assert mock_task.call_count == 2


@pytest.mark.asyncio
async def test_batch_render_partial_failure_reports_errors(client, db_session, tmp_path):
    pid, cid_ok = await _create_project_with_clip(db_session, tmp_path)
    project = (await db_session.execute(
        select(Project).where(Project.id == pid).options(selectinload(Project.transcription))
    )).scalar_one()
    cid_no_audio = await _add_clip_to_project(db_session, project, tmp_path, with_audio=False)
    with patch("app.routers.vertical._do_render_vertical", new_callable=AsyncMock):
        resp = await client.post(
            f"/api/v1/projects/{pid}/vertical/batch",
            json={"clip_ids": [cid_ok, cid_no_audio, 99999], "request": {}},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["render_ids"]) == 1
    assert {e["clip_id"] for e in data["errors"]} == {cid_no_audio, 99999}


@pytest.mark.asyncio
async def test_batch_render_empty_clip_ids_rejected(client, db_session, tmp_path):
    pid, _ = await _create_project_with_clip(db_session, tmp_path)
    resp = await client.post(
        f"/api/v1/projects/{pid}/vertical/batch",
        json={"clip_ids": [], "request": {}},
    )
    assert resp.status_code == 422


# ── Draft preview ──────────────────────────────────────────────────────────────

async def _fake_render_vertical(**kwargs):
    from app.services.vertical_editor_service import RenderResult
    out = kwargs["output_path"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"fake-mp4-bytes")
    return RenderResult(output_path=str(out), duration=5.0, file_size=len(b"fake-mp4-bytes"),
                         width=1080, height=1920, processing_time=0.1)


@pytest.mark.asyncio
async def test_draft_clip_not_found(client, db_session, tmp_path):
    pid, _ = await _create_project_with_clip(db_session, tmp_path)
    resp = await client.post(f"/api/v1/projects/{pid}/clips/99999/vertical/draft", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_draft_no_audio(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path, with_audio=False)
    resp = await client.post(f"/api/v1/projects/{pid}/clips/{cid}/vertical/draft", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_draft_no_transcription_segments(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path, with_transcription=False)
    resp = await client.post(f"/api/v1/projects/{pid}/clips/{cid}/vertical/draft", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_draft_success_returns_mp4(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path)
    with patch("app.routers.vertical.render_vertical", side_effect=_fake_render_vertical):
        resp = await client.post(f"/api/v1/projects/{pid}/clips/{cid}/vertical/draft", json={})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"


@pytest.mark.asyncio
async def test_draft_render_failure_returns_500(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path)
    with patch("app.routers.vertical.render_vertical", new_callable=AsyncMock) as mock_render:
        mock_render.side_effect = RuntimeError("ffmpeg exploded")
        resp = await client.post(f"/api/v1/projects/{pid}/clips/{cid}/vertical/draft", json={})
    assert resp.status_code == 500


# ── List / get / delete renders ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_project_verticals_empty(client, db_session, tmp_path):
    pid, _ = await _create_project_with_clip(db_session, tmp_path)
    resp = await client.get(f"/api/v1/projects/{pid}/vertical")
    assert resp.status_code == 200
    assert resp.json()["renders"] == []


@pytest.mark.asyncio
async def test_list_clip_verticals(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path)
    db_session.add(VerticalRender(clip_id=cid, project_id=pid, status=VerticalRenderStatus.COMPLETED))
    await db_session.commit()
    resp = await client.get(f"/api/v1/projects/{pid}/clips/{cid}/vertical")
    assert resp.status_code == 200
    assert len(resp.json()["renders"]) == 1


@pytest.mark.asyncio
async def test_get_vertical_render_not_found(client, db_session, tmp_path):
    pid, _ = await _create_project_with_clip(db_session, tmp_path)
    resp = await client.get(f"/api/v1/projects/{pid}/vertical/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_vertical_render(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path)
    vr = VerticalRender(clip_id=cid, project_id=pid, status=VerticalRenderStatus.COMPLETED)
    db_session.add(vr)
    await db_session.commit()
    resp = await client.delete(f"/api/v1/projects/{pid}/vertical/{vr.id}")
    assert resp.status_code == 200
    assert (await client.get(f"/api/v1/projects/{pid}/vertical/{vr.id}")).status_code == 404


@pytest.mark.asyncio
async def test_delete_vertical_render_not_found(client, db_session, tmp_path):
    pid, _ = await _create_project_with_clip(db_session, tmp_path)
    resp = await client.delete(f"/api/v1/projects/{pid}/vertical/99999")
    assert resp.status_code == 404


# ── Download ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_render_not_ready(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path)
    vr = VerticalRender(clip_id=cid, project_id=pid, status=VerticalRenderStatus.PROCESSING)
    db_session.add(vr)
    await db_session.commit()
    resp = await client.get(f"/api/v1/projects/{pid}/vertical/{vr.id}/download")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_download_render_missing_file(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path)
    vr = VerticalRender(clip_id=cid, project_id=pid, status=VerticalRenderStatus.COMPLETED,
                         output_path=str(tmp_path / "missing.mp4"))
    db_session.add(vr)
    await db_session.commit()
    resp = await client.get(f"/api/v1/projects/{pid}/vertical/{vr.id}/download")
    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_download_render_success(client, db_session, tmp_path):
    pid, cid = await _create_project_with_clip(db_session, tmp_path)
    out = tmp_path / "render.mp4"
    out.write_bytes(b"fake-mp4-bytes")
    vr = VerticalRender(clip_id=cid, project_id=pid, status=VerticalRenderStatus.COMPLETED, output_path=str(out))
    db_session.add(vr)
    await db_session.commit()
    resp = await client.get(f"/api/v1/projects/{pid}/vertical/{vr.id}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"


# ── Watermark upload ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_watermark_success_path_field_is_real(client):
    # Regression test: upload_watermark() used to reference an undefined
    # `target_path` variable in the response (NameError on every call).
    resp = await client.post(
        "/api/v1/vertical/watermark/upload",
        files={"file": ("logo.png", b"\x89PNG\r\n fake png bytes", "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"]
    from pathlib import Path
    assert Path(data["path"]).exists()


@pytest.mark.asyncio
async def test_upload_watermark_invalid_extension(client):
    resp = await client.post(
        "/api/v1/vertical/watermark/upload",
        files={"file": ("logo.txt", b"not an image", "text/plain")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_watermark_too_large(client):
    big = b"0" * (2 * 1024 * 1024 + 1)
    resp = await client.post(
        "/api/v1/vertical/watermark/upload",
        files={"file": ("logo.png", big, "image/png")},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_serve_watermark_not_found(client):
    resp = await client.get("/api/v1/vertical/watermark/file/does-not-exist.png")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_serve_watermark_path_traversal_rejected(client):
    # Use a backslash (not a forward slash) so the value still matches a
    # single Starlette path segment and reaches our own ".." / "\\" check
    # instead of 404-ing at the router level.
    resp = await client.get("/api/v1/vertical/watermark/file/..%5Cetc%5Cpasswd")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_serve_watermark_after_upload(client):
    upload = await client.post(
        "/api/v1/vertical/watermark/upload",
        files={"file": ("logo.png", b"fake png bytes", "image/png")},
    )
    file_id = upload.json()["file_id"]
    resp = await client.get(f"/api/v1/vertical/watermark/file/{file_id}")
    assert resp.status_code == 200
