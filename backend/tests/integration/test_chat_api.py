import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
class TestChatAPI:
    async def _create_project_with_transcription(self, client, db_session):
        from app.models.project import Project, Transcription, ProjectStatus, TranscriptionStatus
        from datetime import datetime

        project = Project(name="Chat Test Project", status=ProjectStatus.COMPLETED)
        db_session.add(project)
        await db_session.flush()

        transcription = Transcription(
            project_id=project.id,
            status=TranscriptionStatus.COMPLETED,
            text="The speaker discussed machine learning and artificial intelligence in depth. "
                 "They mentioned that AI will transform healthcare within 5 years. "
                 "The main focus was on neural networks and deep learning applications.",
            language_detected="en",
            word_count=35,
        )
        db_session.add(transcription)
        await db_session.commit()
        return project.id

    async def test_chat_requires_transcription(self, client):
        create = await client.post("/api/v1/projects", json={"name": "No Transcription"})
        pid = create.json()["id"]

        resp = await client.post(
            f"/api/v1/projects/{pid}/chat",
            json={"message": "What is this about?", "model": "qwen3:14b"},
        )
        assert resp.status_code == 400

    async def test_chat_with_mock_ai(self, client, db_session):
        pid = await self._create_project_with_transcription(client, db_session)

        with patch("app.routers.chat.ai_service.chat_with_context", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = "The content is about machine learning and AI."

            resp = await client.post(
                f"/api/v1/projects/{pid}/chat",
                json={"message": "What is this about?", "model": "qwen3:14b"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "model_used" in data
        assert data["model_used"] == "qwen3:14b"

    async def test_get_chat_history_empty(self, client, db_session):
        pid = await self._create_project_with_transcription(client, db_session)
        resp = await client.get(f"/api/v1/projects/{pid}/chat/history")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_clear_chat_history(self, client, db_session):
        pid = await self._create_project_with_transcription(client, db_session)

        with patch("app.routers.chat.ai_service.chat_with_context", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = "Test response."
            await client.post(
                f"/api/v1/projects/{pid}/chat",
                json={"message": "Test question", "model": "qwen3:14b"},
            )

        history = await client.get(f"/api/v1/projects/{pid}/chat/history")
        assert len(history.json()) > 0

        clear = await client.delete(f"/api/v1/projects/{pid}/chat/history")
        assert clear.status_code == 200

        history_after = await client.get(f"/api/v1/projects/{pid}/chat/history")
        assert len(history_after.json()) == 0
