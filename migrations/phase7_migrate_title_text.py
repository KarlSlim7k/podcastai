"""Add title_text column to vertical_presets table (Phase 6.1 hotfix).

SQLAlchemy create_all() does not ALTER existing tables — it only creates
new ones. So when we add a new column to a model, the dev DB needs an
explicit migration. In production we'd use Alembic; for the local
SQLite this is fine.

Run with:  cd backend && .venv/Scripts/python.exe tests/phase7_migrate_title_text.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as db:
        # Check if column already exists
        r = await db.execute(text("PRAGMA table_info(vertical_presets)"))
        cols = {row[1] for row in r.fetchall()}
        if "title_text" in cols:
            print("title_text column already exists — no migration needed.")
            return

        # Add the column
        print("Adding title_text column to vertical_presets...")
        await db.execute(text(
            "ALTER TABLE vertical_presets ADD COLUMN title_text VARCHAR(500)"
        ))
        await db.commit()
        print("✓ Migration complete.")

        # Verify
        r = await db.execute(text("PRAGMA table_info(vertical_presets)"))
        cols = {row[1] for row in r.fetchall()}
        assert "title_text" in cols
        print("✓ Column verified: title_text")


if __name__ == "__main__":
    asyncio.run(main())
