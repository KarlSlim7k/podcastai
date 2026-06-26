"""
End-to-end tests simulating the complete application flow.
External dependencies (FFmpeg, Whisper, Ollama) are mocked.
Uses a session-scoped DB so state persists across the full workflow.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from unittest.mock import AsyncMock, patch

from app.main import app
from app.database import Base, get_db

TEST_DB = "sqlite+aiosqlite:///:memory:"

MOCK_TRANSCRIPT = (
    "Welcome to our podcast about technology and innovation. "
    "Today we discuss artificial intelligence and its impact on various industries. "
    "Our guest is an expert in machine learning who has worked at top tech companies. "
    "We explore how AI is transforming healthcare, education, and entertainment."
)

MOCK_SEGMENTS = [
    {"id": 0, "start": 0.0, "end": 5.0, "text": "Welcome to our podcast about technology.", "words": []},
    {"id": 1, "start": 5.0, "end": 10.0, "text": "Today we discuss artificial intelligence.", "words": []},
    {"id": 2, "start": 10.0, "end": 15.0, "text": "Our guest is an expert in machine learning.", "words": []},
]


@pytest.fixture(scope="module")
def e2e_engine():
    engine = create_async_engine(TEST_DB, connect_args={"check_same_thread": False})
    return engine


@pytest_asyncio.fixture(scope="module")
async def e2e_db(e2e_engine):
    async with e2e_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(e2e_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with e2e_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="module")
async def e2e_client(e2e_db):
    async def override_db():
        yield e2e_db

    app.dependency_overrides[get_db] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# Module-level state shared across all tests
_state: dict = {}


@pytest.mark.asyncio
async def test_01_system_health(e2e_client):
    resp = await e2e_client.get("/api/v1/system/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_02_get_analysis_types(e2e_client):
    resp = await e2e_client.get("/api/v1/projects/analysis-types")
    assert resp.status_code == 200
    types = resp.json()["types"]
    assert "executive_summary" in types
    assert "main_topics" in types
    assert "blog_article" in types
    assert len(types) >= 17


@pytest.mark.asyncio
async def test_03_create_project(e2e_client):
    resp = await e2e_client.post(
        "/api/v1/projects",
        json={"name": "E2E Test Podcast", "description": "Full workflow test"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "E2E Test Podcast"
    assert data["status"] == "created"
    _state["project_id"] = data["id"]


@pytest.mark.asyncio
async def test_04_transcription_without_audio(e2e_client):
    pid = _state["project_id"]
    resp = await e2e_client.post(
        f"/api/v1/projects/{pid}/transcribe",
        json={"language": "en", "beam_size": 5, "model": "large-v3"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_05_analysis_without_transcription(e2e_client):
    pid = _state["project_id"]
    resp = await e2e_client.post(
        f"/api/v1/projects/{pid}/analyze",
        json={"analysis_types": ["executive_summary"], "model": "qwen3:14b"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_06_inject_mock_transcription(e2e_db, e2e_client):
    pid = _state["project_id"]
    from app.models.project import Project, Transcription, TranscriptionStatus, ProjectStatus
    from sqlalchemy import select

    result = await e2e_db.execute(select(Project).where(Project.id == pid))
    project = result.scalar_one()
    project.status = ProjectStatus.COMPLETED
    project.audio_file = "/mock/audio.wav"
    project.audio_duration = 120.0
    await e2e_db.flush()

    transcription = Transcription(
        project_id=pid,
        status=TranscriptionStatus.COMPLETED,
        model_used="large-v3",
        language_detected="en",
        text=MOCK_TRANSCRIPT,
        segments=MOCK_SEGMENTS,
        word_count=len(MOCK_TRANSCRIPT.split()),
        processing_time=45.2,
    )
    e2e_db.add(transcription)
    await e2e_db.flush()

    resp = await e2e_client.get(f"/api/v1/projects/{pid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["transcription"] is not None
    assert data["transcription"]["status"] == "completed"


@pytest.mark.asyncio
async def test_07_run_single_analysis(e2e_client):
    pid = _state["project_id"]

    with patch("app.routers.analysis.ai_service.analyze_transcript", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = (
            "This podcast episode covers AI technology and innovation, "
            "featuring an expert in machine learning.",
            2.5,
        )
        resp = await e2e_client.post(
            f"/api/v1/projects/{pid}/analyze/single",
            json={"analysis_type": "executive_summary", "model": "qwen3:14b"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["analysis_type"] == "executive_summary"
    assert data["content"] is not None
    assert data["model_used"] == "qwen3:14b"


@pytest.mark.asyncio
async def test_08_chat_with_transcript(e2e_client):
    pid = _state["project_id"]

    with patch("app.routers.chat.ai_service.chat_with_context", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "The guest is described as an expert in machine learning."
        resp = await e2e_client.post(
            f"/api/v1/projects/{pid}/chat",
            json={"message": "Who is the guest?", "model": "qwen3:14b"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert len(data["response"]) > 0


@pytest.mark.asyncio
async def test_09_chat_history_persisted(e2e_client):
    pid = _state["project_id"]
    resp = await e2e_client.get(f"/api/v1/projects/{pid}/chat/history")
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) >= 2
    roles = [m["role"] for m in history]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_10_export_txt(e2e_client):
    pid = _state["project_id"]
    resp = await e2e_client.post(
        f"/api/v1/projects/{pid}/export",
        json={"format": "txt", "include_transcription": True, "include_analyses": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["export_type"] == "txt"
    assert data["file_size"] > 0
    _state["export_id"] = data["id"]


@pytest.mark.asyncio
async def test_11_export_markdown(e2e_client):
    pid = _state["project_id"]
    resp = await e2e_client.post(f"/api/v1/projects/{pid}/export", json={"format": "markdown"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_12_export_json(e2e_client):
    pid = _state["project_id"]
    resp = await e2e_client.post(f"/api/v1/projects/{pid}/export", json={"format": "json"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_13_list_exports(e2e_client):
    pid = _state["project_id"]
    resp = await e2e_client.get(f"/api/v1/projects/{pid}/exports")
    assert resp.status_code == 200
    exports = resp.json()
    assert len(exports) >= 3


@pytest.mark.asyncio
async def test_14_delete_project(e2e_client):
    pid = _state["project_id"]
    resp = await e2e_client.delete(f"/api/v1/projects/{pid}")
    assert resp.status_code == 200
    get_resp = await e2e_client.get(f"/api/v1/projects/{pid}")
    assert get_resp.status_code == 404
