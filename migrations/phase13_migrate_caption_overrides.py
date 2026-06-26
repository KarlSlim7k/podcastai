"""Add caption_overrides column to clips table (Vertical Editor Phase 2).

SQLAlchemy create_all() does not ALTER existing tables — it only creates
new ones. So when we add a new column to a model, the dev DB needs an
explicit migration. In production we'd use Alembic; for the local
SQLite this is fine.

Run with:  cd backend && .venv/Scripts/python.exe tests/phase13_migrate_caption_overrides.py
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
        r = await db.execute(text("PRAGMA table_info(clips)"))
        cols = {row[1] for row in r.fetchall()}
        if "caption_overrides" in cols:
            print("caption_overrides column already exists — no migration needed.")
            return

        # Add the column
        print("Adding caption_overrides column to clips...")
        await db.execute(text(
            "ALTER TABLE clips ADD COLUMN caption_overrides TEXT"
        ))
        await db.commit()
        print("✓ Migration complete.")

        # Verify
        r = await db.execute(text("PRAGMA table_info(clips)"))
        cols = {row[1] for row in r.fetchall()}
        assert "caption_overrides" in cols
        print("✓ Column verified: caption_overrides")


if __name__ == "__main__":
    asyncio.run(main())
