import pytest
import pytest_asyncio


@pytest.mark.asyncio
class TestProjectsAPI:
    async def test_create_project(self, client):
        resp = await client.post("/api/v1/projects", json={"name": "Test Project"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Project"
        assert data["status"] == "created"
        assert "id" in data

    async def test_create_project_with_description(self, client):
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "My Podcast", "description": "Episode 42"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["description"] == "Episode 42"

    async def test_list_projects_empty(self, client):
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_projects_after_creation(self, client):
        await client.post("/api/v1/projects", json={"name": "P1"})
        await client.post("/api/v1/projects", json={"name": "P2"})
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_project(self, client):
        create = await client.post("/api/v1/projects", json={"name": "GetMe"})
        pid = create.json()["id"]
        resp = await client.get(f"/api/v1/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == pid

    async def test_get_project_not_found(self, client):
        resp = await client.get("/api/v1/projects/99999")
        assert resp.status_code == 404

    async def test_update_project(self, client):
        create = await client.post("/api/v1/projects", json={"name": "Old Name"})
        pid = create.json()["id"]
        resp = await client.patch(f"/api/v1/projects/{pid}", json={"name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    async def test_delete_project(self, client):
        create = await client.post("/api/v1/projects", json={"name": "ToDelete"})
        pid = create.json()["id"]
        resp = await client.delete(f"/api/v1/projects/{pid}")
        assert resp.status_code == 200
        get_resp = await client.get(f"/api/v1/projects/{pid}")
        assert get_resp.status_code == 404

    async def test_create_project_empty_name(self, client):
        resp = await client.post("/api/v1/projects", json={"name": ""})
        assert resp.status_code == 422

    async def test_pagination(self, client):
        for i in range(5):
            await client.post("/api/v1/projects", json={"name": f"Project {i}"})
        resp = await client.get("/api/v1/projects?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3
