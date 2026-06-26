"""Add broll_placements column to vertical_renders table (Vertical Editor Phase 3).

SQLAlchemy create_all() does not ALTER existing tables — it only creates
new ones. So when we add a new column to a model, the dev DB needs an
explicit migration. In production we'd use Alembic; for the local
SQLite this is fine.

Run with:  cd backend && .venv/Scripts/python.exe tests/phase14_migrate_broll_placements.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("PRAGMA table_info(vertical_renders)"))
        cols = {row[1] for row in r.fetchall()}
        if "broll_placements" in cols:
            print("broll_placements column already exists - no migration needed.")
            return

        print("Adding broll_placements column to vertical_renders...")
        await db.execute(text(
            "ALTER TABLE vertical_renders ADD COLUMN broll_placements TEXT"
        ))
        await db.commit()
        print("Migration complete.")

        r = await db.execute(text("PRAGMA table_info(vertical_renders)"))
        cols = {row[1] for row in r.fetchall()}
        assert "broll_placements" in cols
        print("Column verified: broll_placements")


if __name__ == "__main__":
    asyncio.run(main())
