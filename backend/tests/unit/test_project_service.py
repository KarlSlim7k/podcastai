"""Unit tests for ProjectService (using in-memory SQLite)."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi import HTTPException

from app.database import Base
from app.models.schemas import ProjectCreate, ProjectUpdate
from app.services.project_service import ProjectService

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(TEST_DB, connect_args={"check_same_thread": False})
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def svc():
    return ProjectService()


@pytest.mark.asyncio
async def test_create_returns_project(db, svc):
    p = await svc.create(db, ProjectCreate(name="Test Project"))
    assert p.id is not None
    assert p.name == "Test Project"


@pytest.mark.asyncio
async def test_create_with_description(db, svc):
    p = await svc.create(db, ProjectCreate(name="Ep 42", description="Weekly show"))
    assert p.description == "Weekly show"


@pytest.mark.asyncio
async def test_get_existing_project(db, svc):
    created = await svc.create(db, ProjectCreate(name="FindMe"))
    await db.commit()
    found = await svc.get(db, created.id)
    assert found.id == created.id
    assert found.name == "FindMe"


@pytest.mark.asyncio
async def test_get_missing_project_raises(db, svc):
    with pytest.raises(HTTPException) as exc:
        await svc.get(db, 9999)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_empty(db, svc):
    projects = await svc.list(db)
    assert projects == []


@pytest.mark.asyncio
async def test_list_returns_all(db, svc):
    await svc.create(db, ProjectCreate(name="A"))
    await svc.create(db, ProjectCreate(name="B"))
    await db.commit()
    projects = await svc.list(db)
    assert len(projects) == 2


@pytest.mark.asyncio
async def test_list_pagination(db, svc):
    for i in range(5):
        await svc.create(db, ProjectCreate(name=f"P{i}"))
    await db.commit()
    page = await svc.list(db, skip=0, limit=3)
    assert len(page) == 3


@pytest.mark.asyncio
async def test_update_name(db, svc):
    p = await svc.create(db, ProjectCreate(name="Old"))
    await db.commit()
    updated = await svc.update(db, p.id, ProjectUpdate(name="New"))
    assert updated.name == "New"


@pytest.mark.asyncio
async def test_update_description(db, svc):
    p = await svc.create(db, ProjectCreate(name="P", description="old desc"))
    await db.commit()
    updated = await svc.update(db, p.id, ProjectUpdate(description="new desc"))
    assert updated.description == "new desc"


@pytest.mark.asyncio
async def test_update_missing_raises(db, svc):
    with pytest.raises(HTTPException) as exc:
        await svc.update(db, 9999, ProjectUpdate(name="X"))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_project(db, svc):
    p = await svc.create(db, ProjectCreate(name="ToDelete"))
    await db.commit()
    await svc.delete(db, p.id)
    await db.commit()
    with pytest.raises(HTTPException):
        await svc.get(db, p.id)


@pytest.mark.asyncio
async def test_delete_missing_raises(db, svc):
    with pytest.raises(HTTPException) as exc:
        await svc.delete(db, 9999)
    assert exc.value.status_code == 404
