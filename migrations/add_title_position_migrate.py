"""One-shot DB migration: add the `title_position` column to
``vertical_renders`` and ``vertical_presets``.

Follows the same idempotent pattern as ``phase6_migrate.py`` — safe to run
multiple times (only ALTERs when the column is missing). Additive only: no
existing data is read, renamed, or deleted.
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "app.db"

if not DB_PATH.exists():
    print(f"DB not found: {DB_PATH}")
    sys.exit(1)

con = sqlite3.connect(str(DB_PATH))
cur = con.cursor()

for table in ("vertical_renders", "vertical_presets"):
    existing_cols = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
    if not existing_cols:
        print(f"  · Table {table} does not exist yet (will be created by the app). Skipping.")
        continue
    if "title_position" not in existing_cols:
        cur.execute(
            f"ALTER TABLE {table} ADD COLUMN title_position VARCHAR(10) DEFAULT 'top'"
        )
        print(f"  + Added column: {table}.title_position")
    else:
        print(f"  · Column already exists: {table}.title_position")

con.commit()

print("\n=== Verification ===")
for table in ("vertical_renders", "vertical_presets"):
    cols = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
    if cols:
        print(f"{table}: title_position present = {'title_position' in cols}")
con.close()
print("\nMigration done.")
