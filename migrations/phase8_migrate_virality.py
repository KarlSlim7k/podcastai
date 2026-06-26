"""Add virality_breakdown and virality_reason columns to clips table (Phase 8).

SQLAlchemy create_all() only creates tables, it does not ALTER them. So
when we add a new column to the Clip model we need an explicit migration
to add it to existing DBs.

This script is idempotent: it checks PRAGMA table_info first and skips
if the column already exists.

Run with:  cd backend && .venv/Scripts/python.exe tests/phase8_migrate_virality.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.database import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("PRAGMA table_info(clips)"))
        cols = {row[1] for row in r.fetchall()}

        added = []
        for col_name, col_def in [
            ("virality_breakdown", "TEXT"),
            ("virality_reason", "VARCHAR(500)"),
        ]:
            if col_name in cols:
                print(f"  ✓ {col_name} already exists — skipping")
                continue
            print(f"  + Adding column {col_name} ({col_def})")
            await db.execute(text(f"ALTER TABLE clips ADD COLUMN {col_name} {col_def}"))
            added.append(col_name)
        if added:
            await db.commit()
            print(f"\n✓ Migration complete. Added: {', '.join(added)}")
        else:
            print("\n✓ No migration needed — all columns present.")


if __name__ == "__main__":
    asyncio.run(main())
