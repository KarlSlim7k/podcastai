"""Create social_accounts and social_publications tables (Phase 12).

SQLAlchemy create_all() only creates tables — it doesn't add them to
existing DBs. This script creates the two new tables if they don't
already exist (idempotent).

Run with:  cd backend && .venv/Scripts/python.exe tests/phase12_migrate_social.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.database import AsyncSessionLocal, async_engine
from app.models.project import Base


async def main():
    # Create only the new tables (idempotent)
    print("Creating social_accounts and social_publications tables...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[
            Base.metadata.tables["social_accounts"],
            Base.metadata.tables["social_publications"],
        ])
    print("✓ Tables created (or already exist).")
    # Verify
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND "
            "name IN ('social_accounts', 'social_publications')"
        ))
        tables = {row[0] for row in r.fetchall()}
        if "social_accounts" in tables and "social_publications" in tables:
            print("✓ Verified: both tables exist.")
        else:
            print(f"✗ Missing tables: {tables}")


if __name__ == "__main__":
    asyncio.run(main())
